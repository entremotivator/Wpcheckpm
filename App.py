
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
    """
    Fetch JSON from WordPress REST API and handle errors gracefully.
    
    Args:
        url (str): The endpoint URL to fetch.
        params (Dict[str, Any], optional): Query parameters for the request.
        silent_on_error (bool): If True, suppress error reporting in Streamlit.

    Returns:
        Optional[Any]: Parsed JSON data if successful, else None.
    """
    try:
        res = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
        res.raise_for_status()
        return res.json()  # Successful response
    except requests.HTTPError as e:
        # HTTP error responses (4xx, 5xx)
        error_msg = f"HTTP {res.status_code}: {e}"
        try:
            error_data = res.json()
            if isinstance(error_data, dict):
                error_msg += f"\n{error_data.get('message', res.text)}"
        except Exception:
            error_msg += f"\n{res.text}"
        if not silent_on_error:
            st.error(error_msg)
        return None
    except Exception as e:
        # Non-HTTP errors (network, parsing, etc.)
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
                error_msg += f": {error_data.get(\'message\', str(e))}"
            st.error(error_msg)
        except:
            if \'text/html\' in res.headers.get(\'content-type\', \'\'):
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
            st.error(f"PUT failed: {error_data.get(\'message\', str(e))}")
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
        if exclude_id and k.lower() in [\'id\']:
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
        if hasattr(v, \'item\'):
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
                        st.success(f"✅ Project created successfully! ID: {res.get(\'id\')}")
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
        help="Upload a file with project data. Include \'id\' column for updates."
    )
    
    if uploaded_projects_file:
        file_ext = uploaded_projects_file.name.split(".")[-1].lower()
        
        if file_ext == "json":
            projects_import_data = json.load(uploaded_projects_file)
            if isinstance(projects_import_data, dict):
                projects_import_data = [projects_import_data]
        else:
            df_projects_import = pd.read_csv(uploaded_projects_file)
            projects_import_data = df_projects_import.to_dict(\'records\')
        
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
                default=[f for f in default_project_fields if f in available_fields]
            )
            
            force_project_id = st.checkbox("Force Project ID (for tasks/tasklists)", value=False, help="If checked, all imported tasks/tasklists will be assigned to the currently selected project.")
            
            if force_project_id:
                st.warning("⚠️ This will override any project_id in your CSV for tasks/tasklists.")

        import_projects_btn = st.button("🚀 Start Project Import", type="primary", use_container_width=True)
        
        if import_projects_btn:
            if not projects_import_data:
                st.error("No project data to import.")
            else:
                with st.spinner("Importing projects..."):
                    success_count = 0
                    for idx, item in enumerate(projects_import_data):
                        if projects_test_import and idx > 0:
                            st.info("Test mode: Only processed the first item.")
                            break
                        
                        payload = clean_payload(item, selected_project_fields, exclude_id=False)
                        
                        item_id = payload.get("id")
                        
                        if import_mode == "Create New Only" or (import_mode == "Smart (Create + Update)" and not item_id):
                            # Create new project
                            if "id" in payload: del payload["id"]
                            res = wp_post_json(projects_url, payload)
                            if res: success_count += 1
                        elif import_mode == "Update Existing Only" or (import_mode == "Smart (Create + Update)" and item_id):
                            # Update existing project
                            if item_id:
                                res = wp_put_json(f"{projects_url}/{item_id}", payload)
                                if res: success_count += 1
                            else:
                                st.warning(f"Skipping item {idx+1}: No ID found for update in \'{item.get(\'title\', \'N/A\')}\'.")
                        
                        time.sleep(0.1) # Be nice to the API
                    
                    st.success(f"✅ Successfully imported/updated {success_count} projects.")
                    st.session_state["projects"] = [] # Clear cache to refetch
                    st.rerun()

# -------------------------------------
# TAB 2: TASKS & TASK LISTS
# -------------------------------------
with tab2:
    st.header("📋 Tasks & Task Lists")
    
    # Select Project for Task/Tasklist Operations
    if "projects" not in st.session_state or not st.session_state["projects"]:
        st.warning("Please fetch projects first in the 'WP Projects' tab.")
        selected_project_id = None
        selected_project_title = ""
    else:
        project_titles = {p["id"]: extract_title(p) for p in st.session_state["projects"] if "id" in p}
        selected_project_id = st.selectbox(
            "Select Project",
            options=list(project_titles.keys()),
            format_func=lambda x: project_titles[x],
            key="task_project_select"
        )
        selected_project_title = project_titles.get(selected_project_id, "")

    if selected_project_id:
        st.info(f"Selected Project: **{selected_project_title}** (ID: {selected_project_id})")
        
        # Fetch Task Lists and Tasks for Selected Project
        if st.button(f"🔄 Fetch Task Lists & Tasks for {selected_project_title}"):
            with st.spinner(f"Fetching task lists and tasks for project {selected_project_id}..."):
                task_lists_url = f"{projects_url}/{selected_project_id}/task-lists"
                tasks_url = f"{projects_url}/{selected_project_id}/tasks"
                
                fetched_task_lists = wp_get_json(task_lists_url)
                fetched_tasks = wp_get_json(tasks_url)
                
                st.session_state[f"task_lists_{selected_project_id}"] = fetched_task_lists if isinstance(fetched_task_lists, list) else []
                st.session_state[f"tasks_{selected_project_id}"] = fetched_tasks if isinstance(fetched_tasks, list) else []
                
                st.success(f"✅ Fetched {len(st.session_state[f\"task_lists_{selected_project_id}\"])} task lists and {len(st.session_state[f\"tasks_{selected_project_id}\"])} tasks.")
                if show_raw_json:
                    with st.expander("Raw Task Lists JSON"):
                        st.json(fetched_task_lists)
                    with st.expander("Raw Tasks JSON"):
                        st.json(fetched_tasks)

        # Display Task Lists
        task_lists = st.session_state.get(f"task_lists_{selected_project_id}", [])
        if task_lists:
            st.subheader("📝 Task Lists")
            tl_rows = []
            for tl in task_lists:
                if not isinstance(tl, dict): continue
                tl_rows.append({
                    "ID": tl.get("id"),
                    "Title": extract_title(tl),
                    "Status": tl.get("status") or "",
                    "Task Count": tl.get("task_count") or 0
                })
            st.dataframe(pd.DataFrame(tl_rows), use_container_width=True)
            download_json(task_lists, f"task_lists_project_{selected_project_id}.json", label="⬇️ Download Task Lists JSON")

        # Display Tasks
        tasks = st.session_state.get(f"tasks_{selected_project_id}", [])
        if tasks:
            st.subheader("✅ Tasks")
            task_rows = []
            for task in tasks:
                if not isinstance(task, dict): continue
                task_rows.append({
                    "ID": task.get("id"),
                    "Title": extract_title(task),
                    "Task List": task.get("task_list_title") or "",
                    "Status": task.get("status") or "",
                    "Due Date": task.get("due_date") or ""
                })
            st.dataframe(pd.DataFrame(task_rows), use_container_width=True)
            download_json(tasks, f"tasks_project_{selected_project_id}.json", label="⬇️ Download Tasks JSON")

        st.markdown("---")
        st.subheader("➕ Create New Task List")
        with st.form("create_task_list_form"):
            new_tl_title = st.text_input("Task List Title *", placeholder="Enter task list name")
            new_tl_desc = st.text_area("Description", placeholder="Task list description (optional)")
            create_tl_btn = st.form_submit_button("➕ Create Task List", type="primary", use_container_width=True)
            
            if create_tl_btn:
                if not new_tl_title or new_tl_title.strip() == "":
                    st.error("❌ Task List title is required!")
                else:
                    payload = {
                        "title": new_tl_title.strip(),
                        "description": new_tl_desc,
                        "project_id": selected_project_id
                    }
                    with st.spinner("Creating task list..."):
                        res = wp_post_json(f"{projects_url}/{selected_project_id}/task-lists", payload)
                        if res:
                            st.success(f"✅ Task List created successfully! ID: {res.get(\'id\')}")
                            if show_raw_json:
                                st.json(res)
                            time.sleep(1)
                            st.rerun()

        st.markdown("---")
        st.subheader("➕ Create New Task")
        with st.form("create_task_form"):
            task_lists_for_dropdown = {tl["id"]: extract_title(tl) for tl in task_lists}
            selected_task_list_id = st.selectbox(
                "Select Task List",
                options=list(task_lists_for_dropdown.keys()),
                format_func=lambda x: task_lists_for_dropdown[x],
                key="task_list_select"
            )
            new_task_title = st.text_input("Task Title *", placeholder="Enter task name")
            new_task_desc = st.text_area("Description", placeholder="Task description (optional)")
            new_task_due_date = st.date_input("Due Date", value=None)
            create_task_btn = st.form_submit_button("➕ Create Task", type="primary", use_container_width=True)
            
            if create_task_btn:
                if not new_task_title or new_task_title.strip() == "":
                    st.error("❌ Task title is required!")
                elif not selected_task_list_id:
                    st.error("❌ Please select a Task List.")
                else:
                    payload = {
                        "title": new_task_title.strip(),
                        "description": new_task_desc,
                        "task_list_id": selected_task_list_id,
                        "project_id": selected_project_id # Ensure project_id is sent
                    }
                    if new_task_due_date:
                        payload["due_date"] = str(new_task_due_date)
                    
                    with st.spinner("Creating task..."):
                        res = wp_post_json(f"{projects_url}/{selected_project_id}/tasks", payload)
                        if res:
                            st.success(f"✅ Task created successfully! ID: {res.get(\'id\')}")
                            if show_raw_json:
                                st.json(res)
                            time.sleep(1)
                            st.rerun()

        st.markdown("---")
        st.subheader("📥 Unified Import: Task Lists & Tasks from One File")
        
        uploaded_unified_file = st.file_uploader(
            "Upload Unified CSV (Task Lists & Tasks)", 
            type=["csv"], 
            key="upload_unified_bulk",
            help="Upload a CSV file containing both task lists and tasks. Must have a 'type' column (tasklist/task)."
        )
        
        if uploaded_unified_file:
            df_unified_import = pd.read_csv(uploaded_unified_file)
            unified_import_data = df_unified_import.to_dict(\'records\')
            
            st.write(f"**Preview** ({len(unified_import_data)} items):")
            st.dataframe(pd.DataFrame(unified_import_data).head(10), use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                unified_import_mode = st.radio(
                    "Import Mode",
                    ["Create New Only", "Update Existing Only", "Smart (Create + Update)"],
                    key="unified_import_mode",
                    help="Create: Ignores ID. Update: Only items with ID. Smart: Creates if no ID, updates if ID exists."
                )
            with col2:
                unified_test_import = st.checkbox("Test with first item", value=True, key="test_unified_import")
            
            force_current_project_id = st.checkbox(
                "Force Current Project ID", 
                value=True, 
                help="If checked, all imported task lists and tasks will be assigned to the currently selected project."
            )
            
            if force_current_project_id:
                st.warning(f"⚠️ All imported items will be assigned to Project ID: {selected_project_id}")

            start_unified_import_btn = st.button("🚀 Start Unified Import", type="primary", use_container_width=True)
            
            if start_unified_import_btn:
                if not unified_import_data:
                    st.error("No data to import.")
                else:
                    with st.spinner("Importing unified data..."):
                        task_list_success = 0
                        task_success = 0
                        
                        # Cache task list IDs by title for task assignment
                        task_list_id_map = {}
                        for tl in task_lists:
                            task_list_id_map[extract_title(tl)] = tl["id"]

                        for idx, item in enumerate(unified_import_data):
                            if unified_test_import and idx > 0:
                                st.info("Test mode: Only processed the first item.")
                                break
                            
                            item_type = item.get("type")
                            if not item_type:
                                st.warning(f"Skipping item {idx+1}: No 'type' specified. Item: {item.get(\'title\', \'N/A\')}")
                                continue
                            
                            payload = clean_payload(item, [], exclude_id=False) # Clean all fields
                            
                            # Ensure description is a string, handling NaN values
                            if 'description' in payload:
                                if pd.isna(payload['description']):
                                    payload['description'] = ''
                                else:
                                    payload['description'] = str(payload['description'])

                            # Handle date fields (start_at, due_date) - ensure they are strings or empty strings
                            for date_field in ['start_at', 'due_date']:
                                if date_field in payload:
                                    if pd.isna(payload[date_field]) or payload[date_field] is None:
                                        payload[date_field] = ''
                                    else:
                                        payload[date_field] = str(payload[date_field])
                                else:
                                    payload[date_field] = '' # Ensure field exists even if not in CSV

                            # Force project_id if checked
                            if force_current_project_id and selected_project_id:
                                payload["project_id"] = selected_project_id
                            elif "project_id" not in payload or pd.isna(payload["project_id"]):
                                # If not forced and not present, assign to selected project as fallback
                                payload["project_id"] = selected_project_id

                            item_id = payload.get("id")
                            
                            if item_type == "tasklist":
                                if unified_import_mode == "Create New Only" or (unified_import_mode == "Smart (Create + Update)" and not item_id):
                                    if "id" in payload: del payload["id"]
                                    res = wp_post_json(f"{projects_url}/{payload[\'project_id\']}/task-lists", payload)
                                    if res:
                                        task_list_success += 1
                                        task_list_id_map[extract_title(res)] = res["id"] # Update map for new task lists
                                elif unified_import_mode == "Update Existing Only" or (unified_import_mode == "Smart (Create + Update)" and item_id):
                                    if item_id:
                                        res = wp_put_json(f"{projects_url}/{payload[\'project_id\']}/task-lists/{item_id}", payload)
                                        if res: task_list_success += 1
                                    else:
                                        st.warning(f"Skipping task list {idx+1}: No ID found for update in \'{item.get(\'title\', \'N/A\')}\'.")
                            
                            elif item_type == "task":
                                # Assign task to task list
                                task_list_name = item.get("task_list_name")
                                if task_list_name and task_list_name in task_list_id_map:
                                    payload["task_list_id"] = task_list_id_map[task_list_name]
                                elif task_list_name:
                                    st.warning(f"Task \'{item.get(\'title\', \'N/A\')}\' refers to unknown task list \'{task_list_name}\'. Skipping.")
                                    continue
                                else:
                                    st.warning(f"Task \'{item.get(\'title\', \'N/A\')}\' has no \'task_list_name\'. Skipping.")
                                    continue

                                if unified_import_mode == "Create New Only" or (unified_import_mode == "Smart (Create + Update)" and not item_id):
                                    if "id" in payload: del payload["id"]
                                    res = wp_post_json(f"{projects_url}/{payload[\'project_id\']}/tasks", payload)
                                    if res: task_success += 1
                                elif unified_import_mode == "Update Existing Only" or (unified_import_mode == "Smart (Create + Update)" and item_id):
                                    if item_id:
                                        res = wp_put_json(f"{projects_url}/{payload[\'project_id\']}/tasks/{item_id}", payload)
                                        if res: task_success += 1
                                    else:
                                        st.warning(f"Skipping task {idx+1}: No ID found for update in \'{item.get(\'title\', \'N/A\')}\'.")
                            
                            time.sleep(0.1) # Be nice to the API
                        
                        st.success(f"✅ Successfully imported {task_list_success} task lists and {task_success} tasks.")
                        st.session_state[f"task_lists_{selected_project_id}"] = [] # Clear cache to refetch
                        st.session_state[f"tasks_{selected_project_id}"] = [] # Clear cache to refetch
                        st.rerun()

# -------------------------------------
# TAB 3: CUSTOM POST TYPES
# -------------------------------------
with tab3:
    st.header("🧱 Custom Post Types")
    
    cpt_type = st.text_input("Custom Post Type Slug", "post", help="e.g., 'post', 'page', 'product', 'event'")
    cpt_url = f"{posts_url}/{cpt_type}"
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        fetch_cpt_btn = st.button(f"🔄 Fetch All {cpt_type.title()}s", use_container_width=True)
    with col2:
        if st.session_state.get(f"cpt_{cpt_type}"):
            clear_cpt_btn = st.button("🗑️ Clear", key=f"clear_cpt_{cpt_type}", use_container_width=True)
            if clear_cpt_btn:
                st.session_state[f"cpt_{cpt_type}"] = []
                st.rerun()

    if fetch_cpt_btn:
        with st.spinner(f"Fetching {cpt_type}s from WordPress..."):
            all_cpts = fetch_all_pages(cpt_url)
            st.session_state[f"cpt_{cpt_type}"] = all_cpts
            st.success(f"✅ Fetched {len(all_cpts)} {cpt_type}s.")
            
            if show_raw_json:
                with st.expander("Raw JSON Response"):
                    st.json(all_cpts)

    cpts = st.session_state.get(f"cpt_{cpt_type}", [])
    
    if cpts:
        st.subheader(f"📊 {cpt_type.title()}s Overview ({len(cpts)} total)")
        
        cpt_rows = []
        for p in cpts:
            if not isinstance(p, dict): continue
            desc = p.get("content") or ""
            if isinstance(desc, dict):
                desc = desc.get("rendered", "")
            desc_preview = str(desc)[:50] + "..." if desc else ""
            
            cpt_rows.append({
                "ID": p.get("id"),
                "Title": extract_title(p),
                "Status": p.get("status") or "",
                "Date": p.get("date") or "",
                "Content Preview": desc_preview
            })
        
        df_cpt = pd.DataFrame(cpt_rows)
        st.dataframe(df_cpt, use_container_width=True, height=400)
        
        col1, col2 = st.columns(2)
        with col1:
            download_json(cpts, f"wp_{cpt_type}s.json", label=f"⬇️ Download {cpt_type.title()}s JSON")
        
        with col2:
            csv_cpt = df_cpt.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"⬇️ Download {cpt_type.title()}s CSV",
                data=csv_cpt,
                file_name=f"wp_{cpt_type}s.csv",
                mime="text/csv"
            )

    # Create New CPT
    st.markdown("---")
    st.subheader(f"➕ Create New {cpt_type.title()}")
    
    with st.form(f"create_cpt_form_{cpt_type}"):
        new_cpt_title = st.text_input(f"{cpt_type.title()} Title *", placeholder=f"Enter {cpt_type} title")
        new_cpt_content = st.text_area("Content", placeholder=f"{cpt_type.title()} content (optional)", height=200)
        new_cpt_status = st.selectbox("Status", ["publish", "draft", "pending", "private"], index=0)
        
        create_cpt_btn = st.form_submit_button(f"➕ Create {cpt_type.title()}", type="primary", use_container_width=True)
        
        if create_cpt_btn:
            if not new_cpt_title or new_cpt_title.strip() == "":
                st.error(f"❌ {cpt_type.title()} title is required!")
            else:
                payload = {
                    "title": new_cpt_title.strip(),
                    "content": new_cpt_content,
                    "status": new_cpt_status,
                }
                with st.spinner(f"Creating {cpt_type}..."):
                    res = wp_post_json(cpt_url, payload)
                    if res:
                        st.success(f"✅ {cpt_type.title()} created successfully! ID: {res.get(\'id\')}")
                        if show_raw_json:
                            st.json(res)
                        time.sleep(1)
                        st.rerun()

    # Bulk Import CPTs
    st.markdown("---")
    st.subheader(f"📥 Bulk Import/Update {cpt_type.title()}s")
    
    uploaded_cpt_file = st.file_uploader(
        f"Upload {cpt_type.title()}s CSV/JSON", 
        type=["csv", "json"], 
        key=f"upload_cpt_bulk_{cpt_type}",
        help="Upload a file with CPT data. Include \'id\' column for updates."
    )
    
    if uploaded_cpt_file:
        file_ext = uploaded_cpt_file.name.split(".")[-1].lower()
        
        if file_ext == "json":
            cpt_import_data = json.load(uploaded_cpt_file)
            if isinstance(cpt_import_data, dict):
                cpt_import_data = [cpt_import_data]
        else:
            df_cpt_import = pd.read_csv(uploaded_cpt_file)
            cpt_import_data = df_cpt_import.to_dict(\'records\')
        
        st.write(f"**Preview** ({len(cpt_import_data)} items):")
        st.dataframe(pd.DataFrame(cpt_import_data).head(10), use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            cpt_import_mode = st.radio(
                "Import Mode",
                ["Create New Only", "Update Existing Only", "Smart (Create + Update)"],
                key=f"cpt_import_mode_{cpt_type}"
            )
        with col2:
            cpt_test_import = st.checkbox("Test with first item", value=True, key=f"test_cpt_import_{cpt_type}")
        
        with st.expander("⚙️ Field Selection & Options"):
            available_cpt_fields = list(cpt_import_data[0].keys()) if cpt_import_data else []
            default_cpt_fields = ["title", "content", "status", "date"]
            
            selected_cpt_fields = st.multiselect(
                "Fields to include:",
                options=available_cpt_fields,
                default=[f for f in default_cpt_fields if f in available_cpt_fields],
                key=f"selected_cpt_fields_{cpt_type}"
            )

        import_cpt_btn = st.button(f"🚀 Start {cpt_type.title()} Import", type="primary", use_container_width=True, key=f"start_cpt_import_{cpt_type}")
        
        if import_cpt_btn:
            if not cpt_import_data:
                st.error(f"No {cpt_type} data to import.")
            else:
                with st.spinner(f"Importing {cpt_type}s..."):
                    success_count = 0
                    for idx, item in enumerate(cpt_import_data):
                        if cpt_test_import and idx > 0:
                            st.info("Test mode: Only processed the first item.")
                            break
                        
                        payload = clean_payload(item, selected_cpt_fields, exclude_id=False)
                        
                        item_id = payload.get("id")
                        
                        if cpt_import_mode == "Create New Only" or (cpt_import_mode == "Smart (Create + Update)" and not item_id):
                            if "id" in payload: del payload["id"]
                            res = wp_post_json(cpt_url, payload)
                            if res: success_count += 1
                        elif cpt_import_mode == "Update Existing Only" or (cpt_import_mode == "Smart (Create + Update)" and item_id):
                            if item_id:
                                res = wp_put_json(f"{cpt_url}/{item_id}", payload)
                                if res: success_count += 1
                            else:
                                st.warning(f"Skipping item {idx+1}: No ID found for update in \'{item.get(\'title\', \'N/A\')}\'.")
                        
                        time.sleep(0.1) # Be nice to the API
                    
                    st.success(f"✅ Successfully imported/updated {success_count} {cpt_type}s.")
                    st.session_state[f"cpt_{cpt_type}"] = [] # Clear cache to refetch
                    st.rerun()

# -------------------------------------
# TAB 4: DB EXPORT/IMPORT (Optional)
# -------------------------------------
with tab4:
    st.header("🗄️ Database Export/Import (Requires PyMySQL)")
    
    if not HAS_PYMYSQL:
        st.warning("PyMySQL is not installed. Please install it (`pip install pymysql`) to use this feature.")
    else:
        st.info("This section is for advanced users to directly interact with the WordPress database.")
        st.markdown("**Use with caution!** Direct DB operations can bypass WordPress logic and cause data inconsistencies.")
        
        db_host = st.text_input("DB Host", "localhost")
        db_user = st.text_input("DB User", "root")
        db_password = st.text_input("DB Password", type="password")
        db_name = st.text_input("DB Name", "wordpress")
        
        db_connection = None
        try:
            db_connection = pymysql.connect(host=db_host, user=db_user, password=db_password, database=db_name)
            st.success("Connected to database!")
        except Exception as e:
            st.error(f"Could not connect to database: {e}")
            db_connection = None

        if db_connection:
            st.subheader("Export Data")
            export_table = st.text_input("Table to Export", "wp_posts")
            if st.button("Export Table to CSV"):
                try:
                    with db_connection.cursor() as cursor:
                        cursor.execute(f"SELECT * FROM {export_table}")
                        result = cursor.fetchall()
                        columns = [desc[0] for desc in cursor.description]
                        df_db = pd.DataFrame(result, columns=columns)
                        csv_db = df_db.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label=f"⬇️ Download {export_table} CSV",
                            data=csv_db,
                            file_name=f"{export_table}.csv",
                            mime="text/csv"
                        )
                        st.success(f"Exported {len(result)} rows from {export_table}.")
                except Exception as e:
                    st.error(f"Error exporting data: {e}")

            st.subheader("Import Data")
            uploaded_db_file = st.file_uploader("Upload CSV to Import", type=["csv"], key="upload_db_import")
            import_table = st.text_input("Table to Import Into", "wp_posts_new")
            
            if uploaded_db_file and import_table:
                df_import_db = pd.read_csv(uploaded_db_file)
                st.write("Preview of data to import:")
                st.dataframe(df_import_db.head())
                
                if st.button("Import Data to DB"):
                    try:
                        with db_connection.cursor() as cursor:
                            # Create table if not exists (simple schema from DataFrame)
                            columns_sql = ", ".join([f"`{col}` TEXT" for col in df_import_db.columns])
                            create_table_sql = f"CREATE TABLE IF NOT EXISTS `{import_table}` ({columns_sql})"
                            cursor.execute(create_table_sql)
                            
                            # Insert data
                            for index, row in df_import_db.iterrows():
                                cols = ", ".join([f"`{col}`" for col in df_import_db.columns])
                                vals = ", ".join(["%s" for _ in df_import_db.columns])
                                insert_sql = f"INSERT INTO `{import_table}` ({cols}) VALUES ({vals})"
                                cursor.execute(insert_sql, tuple(row.values))
                            db_connection.commit()
                            st.success(f"Successfully imported {len(df_import_db)} rows into {import_table}.")
                    except Exception as e:
                        st.error(f"Error importing data: {e}")

        if db_connection:
            db_connection.close()




