"""
Streamlit App: WP Project Manager + Custom Post Types - Enhanced Version
-------------------------------------------------------------------------
Usage:
    pip install -r requirements.txt
    streamlit run app.py

requirements.txt:
    streamlit
    requests
    pandas
    pymysql   # optional, only for DB export/import
"""

import streamlit as st
import requests
import json
import pandas as pd
import time
from typing import Dict, Any, Optional, List

# Optional DB
try:
    import pymysql
    HAS_PYMYSQL = True
except Exception:
    HAS_PYMYSQL = False

# Page setup
st.set_page_config(
    page_title="WP Project Manager + CPT Explorer",
    layout="wide",
    page_icon="🧩"
)

# -------------------------------------
# Sidebar: WordPress Connection
# -------------------------------------
st.sidebar.title("🔐 WordPress Connection")

wp_base = st.sidebar.text_input("WordPress Site URL", "https://videmiservices.com").rstrip("/")
wp_user = st.sidebar.text_input("Username or Email")
wp_app_password = st.sidebar.text_input("App Password", type="password", help="Use WordPress App Passwords under Users → Profile → App Passwords")

auth = None
headers = {"Accept": "application/json"}
if wp_user and wp_app_password:
    auth = (wp_user, wp_app_password)

st.sidebar.markdown("---")
st.sidebar.markdown("**Options**")
api_ns = st.sidebar.text_input("Project Manager API Namespace", "pm/v2")
include_tasks = st.sidebar.checkbox("Include Task Lists & Tasks", value=True, help="If checked, task lists and tasks will be fetched for all projects in the 'WP Projects' tab.")
show_raw_json = st.sidebar.checkbox("Show Raw JSON Responses", value=False)

# API URLs
projects_url = f"{wp_base}/wp-json/{api_ns}/projects"
posts_url = f"{wp_base}/wp-json/wp/v2"

st.title("🧩 WP Project Manager + Custom Post Explorer")
st.caption("Fetch, export, import, and edit WordPress Project Manager data and all custom post types using REST API + App Password authentication.")

# -------------------------------------
# Helper functions
# -------------------------------------
def wp_get_json(url: str, params: Dict[str, Any] = None, silent_on_error: bool = False) -> Optional[Any]:
    """Fetch JSON from WordPress REST API."""
    try:
        res = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
        res.raise_for_status()
        return res.json()
    except requests.HTTPError as e:
        if not silent_on_error:
            error_msg = f"HTTP {res.status_code}: {e}"
            try:
                error_data = res.json()
                if isinstance(error_data, dict):
                    error_msg += f"\n{error_data.get('message', res.text)}"
            except:
                error_msg += f"\n{res.text}"
            st.error(error_msg)
        return None
    except Exception as e:
        if not silent_on_error:
            st.error(f"Error connecting to {url}: {e}")
        return None

def wp_post_json(url: str, data: Dict[str, Any]) -> Optional[Any]:
    """Create a new resource via POST request."""
    try:
        res = requests.post(url, headers=headers, auth=auth, json=data, timeout=30)
        res.raise_for_status()
        return res.json()
    except requests.HTTPError as e:
        error_msg = f"POST failed with HTTP {res.status_code}"
        try:
            error_data = res.json()
            if isinstance(error_data, dict):
                error_msg += f": {error_data.get('message', str(e))}"
            st.error(error_msg)
        except:
            if 'text/html' in res.headers.get('content-type', ''):
                st.error(f"{error_msg}: WordPress returned an HTML error page (likely a PHP fatal error)")
                with st.expander("View Error Details"):
                    st.code(res.text[:1000])
            else:
                st.error(f"{error_msg}: {res.text[:500]}")
        return None
    except Exception as e:
        st.error(f"POST failed: {e}")
        return None

def wp_put_json(url: str, data: Dict[str, Any]) -> Optional[Any]:
    """Update an existing resource via PUT request."""
    try:
        res = requests.put(url, headers=headers, auth=auth, json=data, timeout=30)
        res.raise_for_status()
        return res.json()
    except requests.HTTPError as e:
        try:
            error_data = res.json()
            st.error(f"PUT failed: {error_data.get('message', str(e))}")
        except:
            st.error(f"PUT failed: {e}\n{res.text}")
        return None
    except Exception as e:
        st.error(f"PUT failed: {e}")
        return None

def wp_delete_json(url: str) -> Optional[Any]:
    """Delete a resource via DELETE request."""
    try:
        res = requests.delete(url, headers=headers, auth=auth, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"DELETE failed: {e}")
        return None

def download_json(obj, filename: str, label="Download JSON"):
    """Create a download button for JSON data."""
    b = json.dumps(obj, indent=2).encode("utf-8")
    st.download_button(label=label, data=b, file_name=filename, mime="application/json")

def extract_title(p: dict) -> str:
    """Safely extract the title from WP REST API project or CPT object."""
    t = p.get("title")
    if isinstance(t, dict):
        return t.get("rendered", "")
    elif isinstance(t, str):
        return t
    return p.get("project_title") or p.get("name") or ""

def fetch_all_pages(base_url: str, params: Dict[str, Any] = None) -> List[dict]:
    """Fetch all pages of results from a paginated endpoint."""
    all_items = []
    page = 1
    if params is None:
        params = {}
    
    while True:
        params["page"] = page
        params["per_page"] = 100
        data = wp_get_json(base_url, params=params)
        
        if not data:
            break
            
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            all_items.extend(items)
            if len(items) < 100:
                break
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                items = [item for item in data["data"] if isinstance(item, dict)]
                all_items.extend(items)
                if len(items) < 100:
                    break
            else:
                break
        else:
            break
            
        page += 1
        time.sleep(0.1)
    
    return all_items

def clean_payload(item: dict, selected_fields: List[str], skip_empty: bool = True, exclude_id: bool = True) -> dict:
    """Clean and prepare payload for API submission."""
    payload = {}
    
    for k, v in item.items():
        # Skip ID field if requested
        if exclude_id and k.lower() in ['id']:
            continue
        
        # Only include selected fields
        if selected_fields and k not in selected_fields:
            continue
        
        # Handle NaN and None values
        if skip_empty:
            if isinstance(v, float) and pd.isna(v):
                continue
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
        
        # Convert numpy types to Python types
        if hasattr(v, 'item'):
            v = v.item()
        
        payload[k] = v
    
    return payload

# -------------------------------------
# Tabs
# -------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📁 WP Projects", "📋 Tasks & Lists", "🧱 Custom Post Types", "🗄️ DB Export/Import"])

# -------------------------------------
# TAB 1: WP PROJECT MANAGER
# -------------------------------------
with tab1:
    st.header("📁 WP Project Manager Projects")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        fetch_btn = st.button("🔄 Fetch All Projects", use_container_width=True)
    with col2:
        if st.session_state.get("projects"):
            clear_btn = st.button("🗑️ Clear", use_container_width=True)
            if clear_btn:
                st.session_state["projects"] = []
                st.rerun()
    
    if fetch_btn:
        with st.spinner("Fetching projects from WordPress..."):
            all_projects = fetch_all_pages(projects_url)
            st.session_state["projects"] = all_projects
            st.success(f"✅ Fetched {len(all_projects)} projects.")
            
            if show_raw_json:
                with st.expander("Raw JSON Response"):
                    st.json(all_projects)

    projects = st.session_state.get("projects", [])
    
    if projects:
        st.subheader(f"📊 Projects Overview ({len(projects)} total)")
        
        rows = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            desc = p.get("description") or ""
            if isinstance(desc, dict):
                desc = desc.get("rendered", "")
            desc_preview = str(desc)[:50] + "..." if desc else ""
            
            rows.append({
                "ID": p.get("id"),
                "Title": extract_title(p),
                "Status": p.get("status") or "",
                "Created": p.get("created_at") or p.get("created") or "",
                "Description": desc_preview
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=400)
        
        col1, col2 = st.columns(2)
        with col1:
            download_json(projects, "wp_projects.json", label="⬇️ Download Projects JSON")
        
        with col2:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download Projects CSV",
                data=csv,
                file_name="wp_projects.csv",
                mime="text/csv"
            )

        if include_tasks:
            st.markdown("---")
            if st.button("🔄 Fetch Task Lists & Tasks for All Projects"):
                with st.spinner("Fetching task-lists & tasks..."):
                    success_count = 0
                    permission_errors = 0
                    progress_bar = st.progress(0)
                    
                    for idx, p in enumerate(projects):
                        pid = p.get("id")
                        if pid:
                            task_lists = wp_get_json(f"{projects_url}/{pid}/task-lists", silent_on_error=True)
                            if task_lists is None:
                                task_lists = wp_get_json(f"{wp_base}/wp-json/{api_ns}/projects/{pid}/task_lists", silent_on_error=True)
                            
                            tasks = wp_get_json(f"{projects_url}/{pid}/tasks", silent_on_error=True)
                            if tasks is None:
                                tasks = wp_get_json(f"{wp_base}/wp-json/{api_ns}/task-lists/{pid}/tasks", silent_on_error=True)
                            
                            if task_lists is None and tasks is None:
                                permission_errors += 1
                            else:
                                success_count += 1
                            
                            p["task_lists"] = task_lists if isinstance(task_lists, list) else []
                            p["tasks"] = tasks if isinstance(tasks, list) else []
                        
                        progress_bar.progress((idx + 1) / len(projects))
                    
                    progress_bar.empty()
                    
                    if permission_errors > 0:
                        st.warning(f"⚠️ {permission_errors} project(s) returned permission errors or no data.")
                    if success_count > 0:
                        st.success(f"✅ Successfully fetched tasks for {success_count} project(s).")

    # Create New Project
    st.markdown("---")
    st.subheader("➕ Create New Project")
    
    with st.form("create_project_form"):
        st.markdown("**Basic Information**")
        col1, col2 = st.columns([2, 1])
        with col1:
            new_proj_title = st.text_input("Project Title *", placeholder="Enter project name")
        with col2:
            new_proj_status = st.selectbox("Status", ["active", "pending", "completed", "archived"], index=0)
        
        new_proj_desc = st.text_area("Description", placeholder="Project description (optional)", height=100)
        
        st.markdown("**Additional Details**")
        col1, col2, col3 = st.columns(3)
        with col1:
            new_proj_category = st.text_input("Category ID", placeholder="Optional")
        with col2:
            new_proj_start = st.date_input("Start Date", value=None)
        with col3:
            new_proj_end = st.date_input("End Date", value=None)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            new_proj_budget = st.number_input("Budget", min_value=0.0, value=0.0, step=100.0)
        with col2:
            new_proj_color = st.color_picker("Project Color", "#007bff")
        
        create_btn = st.form_submit_button("➕ Create Project", use_container_width=True, type="primary")
        
        if create_btn:
            if not new_proj_title or new_proj_title.strip() == "":
                st.error("❌ Project title is required!")
            else:
                payload = {
                    "title": new_proj_title.strip(),
                    "status": new_proj_status,
                }
                if new_proj_desc:
                    payload["description"] = new_proj_desc
                if new_proj_category:
                    payload["category_id"] = new_proj_category
                if new_proj_start:
                    payload["start_at"] = str(new_proj_start)
                if new_proj_end:
                    payload["due_date"] = str(new_proj_end)
                if new_proj_budget > 0:
                    payload["budget"] = new_proj_budget
                if new_proj_color:
                    payload["color"] = new_proj_color
                
                with st.spinner("Creating project..."):
                    res = wp_post_json(projects_url, payload)
                    if res:
                        st.success(f"✅ Project created successfully! ID: {res.get('id')}")
                        if show_raw_json:
                            st.json(res)
                        time.sleep(1)
                        st.rerun()

    # Bulk Import Projects
    st.markdown("---")
    st.subheader("📥 Bulk Import/Update Projects")
    
    uploaded_projects_file = st.file_uploader(
        "Upload Projects CSV/JSON", 
        type=["csv", "json"], 
        key="upload_projects_bulk",
        help="Upload a file with project data. Include 'id' column for updates."
    )
    
    if uploaded_projects_file:
        file_ext = uploaded_projects_file.name.split(".")[-1].lower()
        
        if file_ext == "json":
            projects_import_data = json.load(uploaded_projects_file)
            if isinstance(projects_import_data, dict):
                projects_import_data = [projects_import_data]
        else:
            df_projects_import = pd.read_csv(uploaded_projects_file)
            projects_import_data = df_projects_import.to_dict('records')
        
        st.write(f"**Preview** ({len(projects_import_data)} items):")
        st.dataframe(pd.DataFrame(projects_import_data).head(10), use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            import_mode = st.radio(
                "Import Mode",
                ["Create New Only", "Update Existing Only", "Smart (Create + Update)"],
                help="Create: Ignores ID. Update: Only items with ID. Smart: Creates if no ID, updates if ID exists."
            )
        with col2:
            projects_test_import = st.checkbox("Test with first item", value=True, key="test_projects_import")
        
        with st.expander("⚙️ Field Selection & Options"):
            available_fields = list(projects_import_data[0].keys()) if projects_import_data else []
            default_project_fields = ["title", "description", "status", "start_at", "due_date", "category_id", "budget", "color"]
            
            selected_project_fields = st.multiselect(
                "Fields to include:",
                options=available_fields,
                default=[f for f in default_project_fields if f in available_fields],
                key="project_fields_select"
            )
            
            skip_empty_projects = st.checkbox("Skip empty/null values", value=True, key="skip_empty_projects")
        
        if st.button("🚀 Import Projects", use_container_width=True, type="primary", key="import_projects_btn"):
            created_count = 0
            updated_count = 0
            failed_count = 0
            skipped_count = 0
            
            items_to_process = projects_import_data[:1] if projects_test_import else projects_import_data
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, item in enumerate(items_to_process):
                status_text.text(f"Processing project {idx + 1}/{len(items_to_process)}...")
                
                item_id = item.get('id') or item.get('ID')
                
                should_create = False
                should_update = False
                
                if import_mode == "Create New Only":
                    should_create = True
                elif import_mode == "Update Existing Only":
                    if item_id:
                        should_update = True
                    else:
                        skipped_count += 1
                        continue
                else:
                    should_update = bool(item_id)
                    should_create = not bool(item_id)
                
                payload = clean_payload(item, selected_project_fields, skip_empty_projects)
                
                if 'title' not in payload or not payload.get('title'):
                    st.warning(f"Project {idx + 1}: Skipping - missing 'title'")
                    failed_count += 1
                    continue
                
                if projects_test_import:
                    st.write(f"**Project {idx + 1} Action:** {'UPDATE' if should_update else 'CREATE'}")
                    if should_update:
                        st.write(f"**Target ID:** {item_id}")
                    st.json(payload)
                
                if should_update:
                    endpoint = f"{projects_url}/{item_id}"
                    res = wp_put_json(endpoint, payload)
                    if res:
                        updated_count += 1
                        if projects_test_import:
                            st.success(f"✅ Updated project ID {item_id}")
                            st.json(res)
                    else:
                        failed_count += 1
                
                elif should_create:
                    endpoint = projects_url
                    res = wp_post_json(endpoint, payload)
                    if res:
                        created_count += 1
                        if projects_test_import:
                            st.success(f"✅ Created project! New ID: {res.get('id')}")
                            st.json(res)
                    else:
                        failed_count += 1
                
                progress_bar.progress((idx + 1) / len(items_to_process))
                
                if not projects_test_import:
                    time.sleep(0.2)
            
            progress_bar.empty()
            status_text.empty()
            
            st.markdown("### 📊 Import Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("✅ Created", created_count)
            col2.metric("🔄 Updated", updated_count)
            col3.metric("⏭️ Skipped", skipped_count)
            col4.metric("❌ Failed", failed_count)
            
            if not projects_test_import and (created_count > 0 or updated_count > 0):
                if st.button("🔄 Refresh Projects List"):
                    st.rerun()

    # Edit Single Project
    st.markdown("---")
    st.subheader("✏️ Edit Single Project")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        project_id = st.text_input("Enter Project ID", key="edit_project_id")
    with col2:
        load_btn = st.button("📥 Load", use_container_width=True)
    
    if load_btn and project_id:
        with st.spinner("Loading project..."):
            proj = wp_get_json(f"{projects_url}/{project_id}")
            if proj:
                st.session_state["edit_project"] = proj
                st.success("✅ Project loaded")
                if show_raw_json:
                    with st.expander("Raw JSON"):
                        st.json(proj)

    edit_project = st.session_state.get("edit_project")
    if edit_project:
        with st.form("edit_project_form"):
            new_title = st.text_input("Title", extract_title(edit_project))
            new_status = st.selectbox("Status", ["active", "pending", "completed", "archived"], 
                                     index=["active", "pending", "completed", "archived"].index(edit_project.get("status", "active")) if edit_project.get("status") in ["active", "pending", "completed", "archived"] else 0)
            new_desc = st.text_area("Description", edit_project.get("description") or "", height=150)
            
            col1, col2 = st.columns(2)
            with col1:
                save_btn = st.form_submit_button("💾 Save", use_container_width=True)
            with col2:
                delete_btn = st.form_submit_button("🗑️ Delete", use_container_width=True)
            
            if save_btn:
                payload = {"title": new_title, "status": new_status, "description": new_desc}
                res = wp_put_json(f"{projects_url}/{edit_project.get('id')}", payload)
                if res:
                    st.success("✅ Project updated")
                    st.session_state["edit_project"] = res
            
            if delete_btn:
                if st.session_state.get("confirm_delete"):
                    res = wp_delete_json(f"{projects_url}/{edit_project.get('id')}")
                    if res:
                        st.success("✅ Project deleted")
                        st.session_state.pop("edit_project", None)
                        st.session_state.pop("confirm_delete", None)
                        st.rerun()
                else:
                    st.session_state["confirm_delete"] = True
                    st.warning("⚠️ Click Delete again to confirm")

# -------------------------------------
# TAB 2: TASKS & TASK LISTS - UNIFIED IMPORT
# -------------------------------------
with tab2:
    st.header("📋 Task Lists & Tasks Management")
    
    if not projects:
        st.info("👈 Please fetch projects first from the 'WP Projects' tab.")
    else:
        project_options = {f"{p.get('id')} - {extract_title(p)}": p.get("id") for p in projects}
        selected_project_label = st.selectbox("Select Project", options=list(project_options.keys()))
        selected_project_id = project_options[selected_project_label]

        task_lists = st.session_state.get("current_task_lists", [])
        tasks = st.session_state.get("current_tasks", [])
        
        col1, col2 = st.columns(2)
        col1.metric("📝 Task Lists", len(task_lists))
        col2.metric("✅ Tasks", len(tasks))
        st.markdown("---")
        
        # Auto-fetch when project changes
        if selected_project_id and (st.session_state.get("current_project_id") != selected_project_id or not st.session_state.get("current_task_lists") or not st.session_state.get("current_tasks")):
            with st.spinner(f"Fetching data for project {selected_project_id}..."):
                task_lists = fetch_all_pages(f"{projects_url}/{selected_project_id}/task-lists")
                tasks = fetch_all_pages(f"{projects_url}/{selected_project_id}/tasks")
                
                st.session_state["current_task_lists"] = task_lists or []
                st.session_state["current_tasks"] = tasks or []
                st.session_state["current_project_id"] = selected_project_id
                
                if not task_lists and not tasks:
                    st.warning("No data found or permission denied")
                else:
                    st.success(f"✅ Fetched {len(task_lists or [])} task lists, {len(tasks or [])} tasks")
        
        if st.button("🔄 Re-fetch Data", use_container_width=True):
            with st.spinner("Re-fetching..."):
                task_lists = fetch_all_pages(f"{projects_url}/{selected_project_id}/task-lists")
                tasks = fetch_all_pages(f"{projects_url}/{selected_project_id}/tasks")
                
                st.session_state["current_task_lists"] = task_lists or []
                st.session_state["current_tasks"] = tasks or []
                st.session_state["current_project_id"] = selected_project_id
                
                st.success(f"✅ Re-fetched {len(task_lists or [])} task lists, {len(tasks or [])} tasks")
                st.rerun()

        # Display and download current data
        if task_lists:
            st.markdown("---")
            st.subheader("📝 Task Lists")
            df_task_lists = pd.DataFrame(task_lists)
            st.dataframe(df_task_lists, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                download_json(task_lists, f"project_{selected_project_id}_task_lists.json", "⬇️ Download JSON")
            with col2:
                csv_tl = df_task_lists.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Download CSV", csv_tl, f"project_{selected_project_id}_task_lists.csv", "text/csv")
        
        if tasks:
            st.markdown("---")
            st.subheader("✅ Tasks")
            df_tasks = pd.DataFrame(tasks)
            st.dataframe(df_tasks, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                download_json(tasks, f"project_{selected_project_id}_tasks.json", "⬇️ Download JSON")
            with col2:
                csv_t = df_tasks.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Download CSV", csv_t, f"project_{selected_project_id}_tasks.csv", "text/csv")

        # UNIFIED IMPORT SECTION - NEW IMPLEMENTATION
        st.markdown("---")
        st.subheader("📥 Unified Import: Task Lists & Tasks from One File")
        
        st.info("💡 **Upload a single CSV file containing both task lists and tasks!** The file should have a 'type' column with values 'tasklist' or 'task', and tasks should reference their parent task list via 'task_list_name' column.")
        
        uploaded_unified_file = st.file_uploader(
            "Upload Unified CSV/JSON", 
            type=["csv", "json"], 
            key=f"upload_unified_{selected_project_id}",
            help="File containing both task lists and tasks with a 'type' column to differentiate"
        )
        
        if uploaded_unified_file:
            file_ext = uploaded_unified_file.name.split(".")[-1].lower()
            
            if file_ext == "json":
                unified_import_data = json.load(uploaded_unified_file)
                if isinstance(unified_import_data, dict):
                    unified_import_data = [unified_import_data]
            else:
                df_unified = pd.read_csv(uploaded_unified_file)
                unified_import_data = df_unified.to_dict('records')
            
            st.write(f"**Preview** ({len(unified_import_data)} items):")
            st.dataframe(pd.DataFrame(unified_import_data).head(10), use_container_width=True)
            
            # Separate task lists and tasks
            task_lists_data = [item for item in unified_import_data if str(item.get('type', '')).lower() == 'tasklist']
            tasks_data = [item for item in unified_import_data if str(item.get('type', '')).lower() == 'task']
            
            col1, col2 = st.columns(2)
            col1.metric("📝 Task Lists Found", len(task_lists_data))
            col2.metric("✅ Tasks Found", len(tasks_data))
            
            # Import Configuration
            st.markdown("---")
            st.markdown("### ⚙️ Import Configuration")
            
            col_config1, col_config2 = st.columns(2)
            
            with col_config1:
                unified_import_mode = st.radio(
                    "Import Mode",
                    ["Create New Only", "Update Existing Only", "Smart (Create + Update)"],
                    key=f"unified_import_mode_{selected_project_id}",
                    help="Create: Ignores ID. Update: Only items with ID. Smart: Auto-detects based on ID presence."
                )
            
            with col_config2:
                unified_test_import = st.checkbox(
                    "Test Mode (first item of each type)",
                    value=True,
                    key=f"unified_test_import_{selected_project_id}",
                    help="Test with first item of each type before full import"
                )
            
            # IMPORT BUTTON
            st.markdown("---")
            if st.button("🚀 Start Unified Import", use_container_width=True, type="primary", key=f"unified_import_btn_{selected_project_id}"):
                
                # Dictionary to map task list names to their created IDs
                task_list_name_to_id = {}
                
                total_tl_created = 0
                total_tl_updated = 0
                total_tl_failed = 0
                total_tl_skipped = 0
                
                total_t_created = 0
                total_t_updated = 0
                total_t_failed = 0
                total_t_skipped = 0
                
                # PHASE 1: Import Task Lists
                if task_lists_data:
                    st.markdown("### 📝 Phase 1: Importing Task Lists")
                    
                    tl_items = task_lists_data[:1] if unified_test_import else task_lists_data
                    progress_tl = st.progress(0)
                    status_tl = st.empty()
                    
                    for idx, item in enumerate(tl_items):
                        status_tl.text(f"Processing Task List {idx + 1}/{len(tl_items)}...")
                        
                        item_id = item.get('id') or item.get('ID')
                        task_list_name = item.get('title', '')
                        
                        should_create = False
                        should_update = False
                        
                        if unified_import_mode == "Create New Only":
                            should_create = True
                        elif unified_import_mode == "Update Existing Only":
                            if item_id:
                                should_update = True
                            else:
                                total_tl_skipped += 1
                                continue
                        else:
                            should_update = bool(item_id)
                            should_create = not bool(item_id)
                        
                        # Build payload for task list
                        payload = {
                            'title': item.get('title', ''),
                            'description': item.get('description', ''),
                            'project_id': selected_project_id
                        }
                        
                        # Add optional fields
                        if 'order' in item and item['order']:
                            payload['order'] = item['order']
                        if 'status' in item and item['status']:
                            payload['status'] = item['status']
                        if 'milestone_id' in item and item['milestone_id']:
                            payload['milestone_id'] = item['milestone_id']
                        
                        if not payload.get('title'):
                            st.warning(f"Task List {idx + 1}: Skipping - missing 'title'")
                            total_tl_failed += 1
                            continue
                        
                        if unified_test_import:
                            st.write(f"**Task List {idx + 1} Action:** {'UPDATE' if should_update else 'CREATE'}")
                            if should_update:
                                st.write(f"**Target ID:** {item_id}")
                            st.json(payload)
                        
                        if should_update:
                            endpoint = f"{projects_url}/{selected_project_id}/task-lists/{item_id}"
                            res = wp_put_json(endpoint, payload)
                            if res:
                                total_tl_updated += 1
                                task_list_name_to_id[task_list_name] = item_id
                                if unified_test_import:
                                    st.success(f"✅ Updated Task List ID {item_id}")
                                    st.json(res)
                            else:
                                total_tl_failed += 1
                        
                        elif should_create:
                            endpoint = f"{projects_url}/{selected_project_id}/task-lists"
                            res = wp_post_json(endpoint, payload)
                            if res:
                                total_tl_created += 1
                                new_id = res.get('id')
                                task_list_name_to_id[task_list_name] = new_id
                                if unified_test_import:
                                    st.success(f"✅ Created Task List! New ID: {new_id}")
                                    st.json(res)
                            else:
                                total_tl_failed += 1
                        
                        progress_tl.progress((idx + 1) / len(tl_items))
                        
                        if not unified_test_import:
                            time.sleep(0.2)
                    
                    progress_tl.empty()
                    status_tl.empty()
                    
                    st.markdown("#### Task Lists Import Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("✅ Created", total_tl_created)
                    col2.metric("🔄 Updated", total_tl_updated)
                    col3.metric("⏭️ Skipped", total_tl_skipped)
                    col4.metric("❌ Failed", total_tl_failed)
                
                # PHASE 2: Import Tasks
                if tasks_data:
                    st.markdown("---")
                    st.markdown("### ✅ Phase 2: Importing Tasks")
                    
                    t_items = tasks_data[:1] if unified_test_import else tasks_data
                    progress_t = st.progress(0)
                    status_t = st.empty()
                    
                    for idx, item in enumerate(t_items):
                        status_t.text(f"Processing Task {idx + 1}/{len(t_items)}...")
                        
                        item_id = item.get('id') or item.get('ID')
                        task_list_name = item.get('task_list_name', '')
                        
                        should_create = False
                        should_update = False
                        
                        if unified_import_mode == "Create New Only":
                            should_create = True
                        elif unified_import_mode == "Update Existing Only":
                            if item_id:
                                should_update = True
                            else:
                                total_t_skipped += 1
                                continue
                        else:
                            should_update = bool(item_id)
                            should_create = not bool(item_id)
                        
                        # Build payload for task
                        payload = {
                            'title': item.get('title', ''),
                            'description': item.get('description', ''),
                            'project_id': selected_project_id
                        }
                        
                        # Map task_list_name to task_list_id
                        if task_list_name and task_list_name in task_list_name_to_id:
                            payload['task_list_id'] = task_list_name_to_id[task_list_name]
                        elif 'task_list_id' in item and item['task_list_id']:
                            payload['task_list_id'] = item['task_list_id']
                        
                        # Add optional fields
                        optional_fields = ['start_at', 'due_date', 'complexity', 'priority', 'status', 'parent_id', 'order', 'payable', 'recurrent', 'estimation']
                        for field in optional_fields:
                            if field in item and item[field] not in [None, '', 'None']:
                                payload[field] = item[field]
                        
                        if not payload.get('title'):
                            st.warning(f"Task {idx + 1}: Skipping - missing 'title'")
                            total_t_failed += 1
                            continue
                        
                        if unified_test_import:
                            st.write(f"**Task {idx + 1} Action:** {'UPDATE' if should_update else 'CREATE'}")
                            if should_update:
                                st.write(f"**Target ID:** {item_id}")
                            st.json(payload)
                        
                        if should_update:
                            endpoint = f"{projects_url}/{selected_project_id}/tasks/{item_id}"
                            res = wp_put_json(endpoint, payload)
                            if res:
                                total_t_updated += 1
                                if unified_test_import:
                                    st.success(f"✅ Updated Task ID {item_id}")
                                    st.json(res)
                            else:
                                total_t_failed += 1
                        
                        elif should_create:
                            endpoint = f"{projects_url}/{selected_project_id}/tasks"
                            res = wp_post_json(endpoint, payload)
                            if res:
                                total_t_created += 1
                                if unified_test_import:
                                    st.success(f"✅ Created Task! New ID: {res.get('id')}")
                                    st.json(res)
                            else:
                                total_t_failed += 1
                        
                        progress_t.progress((idx + 1) / len(t_items))
                        
                        if not unified_test_import:
                            time.sleep(0.2)
                    
                    progress_t.empty()
                    status_t.empty()
                    
                    st.markdown("#### Tasks Import Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("✅ Created", total_t_created)
                    col2.metric("🔄 Updated", total_t_updated)
                    col3.metric("⏭️ Skipped", total_t_skipped)
                    col4.metric("❌ Failed", total_t_failed)
                
                # Final Summary
                st.markdown("---")
                st.markdown("### 🎉 Overall Import Summary")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("📝 Task Lists Created", total_tl_created)
                col2.metric("📝 Task Lists Updated", total_tl_updated)
                col3.metric("✅ Tasks Created", total_t_created)
                col4.metric("✅ Tasks Updated", total_t_updated)
                
                if not unified_test_import and (total_tl_created > 0 or total_tl_updated > 0 or total_t_created > 0 or total_t_updated > 0):
                    if st.button("🔄 Refresh Data"):
                        st.rerun()

        # Display detailed task lists
        if task_lists:
            st.markdown("---")
            st.subheader("📝 Task Lists Details")
            for tl in task_lists:
                if not isinstance(tl, dict):
                    continue
                tl_title = tl.get("title")
                if isinstance(tl_title, dict):
                    tl_title = tl_title.get("rendered", "")
                
                with st.expander(f"Task List: {tl_title} (ID: {tl.get('id')})"):
                    st.json(tl)

        # Display detailed tasks
        if tasks:
            st.markdown("---")
            st.subheader("✅ Tasks Details")
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                t_title = t.get("title")
                if isinstance(t_title, dict):
                    t_title = t_title.get("rendered", "")
                
                with st.expander(f"Task: {t_title} (ID: {t.get('id')})"):
                    st.json(t)

# -------------------------------------
# TAB 3: CUSTOM POST TYPES
# -------------------------------------
with tab3:
    st.header("🧱 Custom Post Types")
    
    # CPT selection
    cpt_types = wp_get_json(f"{wp_base}/wp-json/wp/v2/types")
    if cpt_types:
        cpt_options = {cpt_types[t]["labels"]["singular_name"]: t for t in cpt_types if cpt_types[t].get("rest_base") and cpt_types[t].get("_links", {}).get("wp:items")}
        
        if not cpt_options:
            st.warning("No custom post types with REST API support found.")
        else:
            selected_cpt_label = st.selectbox("Select Custom Post Type", options=list(cpt_options.keys()))
            selected_cpt_slug = cpt_options[selected_cpt_label]
            
            st.markdown("---")
            st.subheader(f"Posts for {selected_cpt_label}")
            
            if st.button(f"🔄 Fetch All {selected_cpt_label} Posts", key="fetch_cpt_posts"):
                with st.spinner(f"Fetching {selected_cpt_label} posts..."):
                    cpt_posts = fetch_all_pages(f"{posts_url}/{selected_cpt_slug}")
                    st.session_state["current_cpt_posts"] = cpt_posts
                    st.session_state["current_cpt_slug"] = selected_cpt_slug
                    st.success(f"✅ Fetched {len(cpt_posts)} {selected_cpt_label} posts.")
                    if show_raw_json:
                        with st.expander("Raw JSON Response"):
                            st.json(cpt_posts)
            
            current_cpt_posts = st.session_state.get("current_cpt_posts", [])
            current_cpt_slug = st.session_state.get("current_cpt_slug", "")
            
            if current_cpt_posts and current_cpt_slug == selected_cpt_slug:
                df_cpt = pd.DataFrame(current_cpt_posts)
                st.dataframe(df_cpt, use_container_width=True, height=400)
                
                col1, col2 = st.columns(2)
                with col1:
                    download_json(current_cpt_posts, f"{selected_cpt_slug}.json", label=f"⬇️ Download {selected_cpt_label} JSON")
                with col2:
                    csv_cpt = df_cpt.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"⬇️ Download {selected_cpt_label} CSV",
                        data=csv_cpt,
                        file_name=f"{selected_cpt_slug}.csv",
                        mime="text/csv"
                    )
                
                # Import CPT
                st.markdown("---")
                st.subheader(f"📥 Import {selected_cpt_label} Posts")
                
                uploaded_cpt_file = st.file_uploader(
                    f"Upload {selected_cpt_label} CSV/JSON",
                    type=["csv", "json"],
                    key=f"upload_cpt_{selected_cpt_slug}"
                )
                
                if uploaded_cpt_file:
                    file_ext = uploaded_cpt_file.name.split(".")[-1].lower()
                    
                    if file_ext == "json":
                        cpt_import_data = json.load(uploaded_cpt_file)
                        if isinstance(cpt_import_data, dict):
                            cpt_import_data = [cpt_import_data]
                    else:
                        df_cpt_import = pd.read_csv(uploaded_cpt_file)
                        cpt_import_data = df_cpt_import.to_dict('records')
                    
                    st.write(f"**Preview** ({len(cpt_import_data)} items):")
                    st.dataframe(pd.DataFrame(cpt_import_data).head(10), use_container_width=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        cpt_import_mode = st.radio(
                            "Import Mode",
                            ["Create New Only", "Update Existing Only", "Smart (Create + Update)"],
                            key=f"cpt_import_mode_{selected_cpt_slug}"
                        )
                    with col2:
                        cpt_test_import = st.checkbox("Test with first item", value=True, key=f"cpt_test_{selected_cpt_slug}")
                    
                    with st.expander("⚙️ Field Selection"):
                        cpt_available_fields = list(cpt_import_data[0].keys()) if cpt_import_data else []
                        cpt_default_fields = ["title", "content", "status", "excerpt", "featured_media"]
                        
                        selected_cpt_fields = st.multiselect(
                            "Fields to include:",
                            options=cpt_available_fields,
                            default=[f for f in cpt_default_fields if f in cpt_available_fields],
                            key=f"cpt_fields_{selected_cpt_slug}"
                        )
                        
                        skip_empty_cpt = st.checkbox("Skip empty/null values", value=True, key=f"skip_empty_cpt_{selected_cpt_slug}")
                    
                    if st.button(f"🚀 Import {selected_cpt_label}", use_container_width=True, type="primary", key=f"import_cpt_{selected_cpt_slug}"):
                        created = 0
                        updated = 0
                        failed = 0
                        skipped = 0
                        
                        items = cpt_import_data[:1] if cpt_test_import else cpt_import_data
                        
                        progress = st.progress(0)
                        status = st.empty()
                        
                        for idx, item in enumerate(items):
                            status.text(f"Processing {idx + 1}/{len(items)}...")
                            
                            item_id = item.get('id') or item.get('ID')
                            
                            should_create = False
                            should_update = False
                            
                            if cpt_import_mode == "Create New Only":
                                should_create = True
                            elif cpt_import_mode == "Update Existing Only":
                                if item_id:
                                    should_update = True
                                else:
                                    skipped += 1
                                    continue
                            else:
                                should_update = bool(item_id)
                                should_create = not bool(item_id)
                            
                            payload = clean_payload(item, selected_cpt_fields, skip_empty_cpt)
                            
                            if 'title' not in payload and 'content' not in payload:
                                st.warning(f"Row {idx + 1}: Skipping - missing title or content")
                                failed += 1
                                continue
                            
                            if cpt_test_import:
                                st.write(f"**Action:** {'UPDATE' if should_update else 'CREATE'}")
                                if should_update:
                                    st.write(f"**Target ID:** {item_id}")
                                st.json(payload)
                            
                            if should_update:
                                endpoint = f"{posts_url}/{selected_cpt_slug}/{item_id}"
                                res = wp_put_json(endpoint, payload)
                                if res:
                                    updated += 1
                                    if cpt_test_import:
                                        st.success(f"✅ Updated ID {item_id}")
                                        st.json(res)
                                else:
                                    failed += 1
                            
                            elif should_create:
                                endpoint = f"{posts_url}/{selected_cpt_slug}"
                                res = wp_post_json(endpoint, payload)
                                if res:
                                    created += 1
                                    if cpt_test_import:
                                        st.success(f"✅ Created! New ID: {res.get('id')}")
                                        st.json(res)
                                else:
                                    failed += 1
                            
                            progress.progress((idx + 1) / len(items))
                            
                            if not cpt_test_import:
                                time.sleep(0.2)
                        
                        progress.empty()
                        status.empty()
                        
                        st.markdown("### 📊 Import Summary")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("✅ Created", created)
                        col2.metric("🔄 Updated", updated)
                        col3.metric("⏭️ Skipped", skipped)
                        col4.metric("❌ Failed", failed)
                        
                        if not cpt_test_import and (created > 0 or updated > 0):
                            if st.button(f"🔄 Refresh {selected_cpt_label} Posts"):
                                st.rerun()
    else:
        st.error("Unable to fetch post types. Check your connection and permissions.")

# -------------------------------------
# TAB 4: DB EXPORT/IMPORT
# -------------------------------------
with tab4:
    st.header("🗄️ Database Export / Import (Advanced)")
    
    if not HAS_PYMYSQL:
        st.warning("⚠️ Install `pymysql` to enable DB features: `pip install pymysql`")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            db_host = st.text_input("DB Host", "localhost")
            db_user = st.text_input("DB User", "root")
            db_password = st.text_input("DB Password", type="password")
        
        with col2:
            db_name = st.text_input("Database Name", "wordpress")
            db_port = st.number_input("DB Port", value=3306, min_value=1, max_value=65535)
            db_table_prefix = st.text_input("Table Prefix", "wp_")

        if st.button("🔌 Test DB Connection"):
            try:
                con = pymysql.connect(
                    host=db_host, user=db_user, password=db_password,
                    db=db_name, port=int(db_port), connect_timeout=5
                )
                st.success("✅ Connected successfully!")
                
                with con.cursor() as cursor:
                    cursor.execute("SHOW TABLES")
                    tables = [row[0] for row in cursor.fetchall()]
                    st.info(f"Found {len(tables)} tables in database.")
                    with st.expander("View Tables"):
                        st.write(tables)
                
                con.close()
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")
        
        st.markdown("---")
        st.subheader("📤 Export Project Manager Data")
        
        if st.button("Export PM Tables to JSON"):
            try:
                con = pymysql.connect(
                    host=db_host, user=db_user, password=db_password,
                    db=db_name, port=int(db_port)
                )
                
                export_data = {}
                pm_tables = [
                    f"{db_table_prefix}pm_projects",
                    f"{db_table_prefix}pm_task_lists",
                    f"{db_table_prefix}pm_tasks"
                ]
                
                with con.cursor(pymysql.cursors.DictCursor) as cursor:
                    for table in pm_tables:
                        try:
                            cursor.execute(f"SELECT * FROM {table}")
                            export_data[table] = cursor.fetchall()
                            st.success(f"✅ Exported {len(export_data[table])} rows from {table}")
                        except Exception as e:
                            st.warning(f"⚠️ Could not export {table}: {e}")
                
                con.close()
                
                if export_data:
                    download_json(export_data, "pm_database_export.json", label="⬇️ Download Database Export")
                
            except Exception as e:
                st.error(f"❌ Export failed: {e}")

# -------------------------------------
# Footer
# -------------------------------------
st.markdown("---")
st.caption("🚀 Developed for WordPress REST API exploration — supports WP Project Manager and all custom post types. Handles App Password authentication safely.")
