"""
Streamlit App: WP Project Manager + Custom Post Types
-----------------------------------------------------
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
from datetime import datetime

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
wp_app_password = st.sidebar.text_input("App Password", type="password", help="Use WordPress App Passwords under Users → Profile → App Password")

auth = None
headers = {"Accept": "application/json"}
if wp_user and wp_app_password:
    auth = (wp_user, wp_app_password)

st.sidebar.markdown("---")
st.sidebar.markdown("**Options**")
api_ns = st.sidebar.text_input("Project Manager API Namespace", "pm/v2")
include_tasks = st.sidebar.checkbox("Auto-fetch Task Metadata", value=True)
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
        try:
            error_data = res.json()
            st.error(f"POST failed: {error_data.get('message', str(e))}")
        except:
            st.error(f"POST failed: {e}\n{res.text}")
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

def extract_meta_totals(project: dict) -> dict:
    """Extract meta totals from project data."""
    if isinstance(project, dict):
        meta = project.get("meta")
        if isinstance(meta, dict):
            data = meta.get("data")
            if isinstance(data, dict):
                return data
    return {}

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
            items = [item for item in data if isinstance(item, dict)] # Ensure only dicts are added
            all_items.extend(items)
            if len(items) < params.get("per_page", 100): # Use params.get for per_page
                break
        elif isinstance(data, dict):
            # Some endpoints return a single object with a 'data' key, or just the object itself
            if "data" in data and isinstance(data["data"], list):
                items = [item for item in data["data"] if isinstance(item, dict)] # Ensure only dicts are added
                all_items.extend(items)
                # If the 'data' key contains a list, and its length is less than per_page, it's the last page
                if len(items) < params.get("per_page", 100):
                    break
            elif "data" in data and isinstance(data["data"], dict):
                all_items.append(data["data"])
                break
            else:
                # If it's a dictionary but not paginated or has a 'data' key, assume it's a single item
                all_items.append(data)
                break
        else:
            break
            
        page += 1
        time.sleep(0.1)
    
    return all_items

def fetch_project_tasks(project_id, projects_url, wp_base, api_ns, fetch_all_pages):
    task_lists_1 = fetch_all_pages(f"{projects_url}/{project_id}/task-lists")
    task_lists_2 = fetch_all_pages(f"{wp_base}/wp-json/{api_ns}/projects/{project_id}/task-lists")
    task_lists = (task_lists_1 or []) + (task_lists_2 or [])
    
    tasks_1 = fetch_all_pages(f"{projects_url}/{project_id}/tasks")
    tasks_2 = fetch_all_pages(f"{wp_base}/wp-json/{api_ns}/task-lists/{project_id}/tasks")
    tasks = (tasks_1 or []) + (tasks_2 or [])
    return task_lists, tasks

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
        fetch_btn = st.button("🔄 Fetch All Projects", width='stretch')
    with col2:
        if st.session_state.get("projects"):
            clear_btn = st.button("🗑️ Clear", width='stretch')
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
        
        # Show aggregate stats
        total_tasks = 0
        total_complete = 0
        total_incomplete = 0
        total_files = 0
        
        for p in projects:
            meta = extract_meta_totals(p)
            total_tasks += int(meta.get("total_tasks", 0))
            total_complete += int(meta.get("total_complete_tasks", 0))
            total_incomplete += int(meta.get("total_incomplete_tasks", 0))
            total_files += int(meta.get("total_files", 0))
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Tasks", total_tasks)
        col2.metric("Complete", total_complete)
        col3.metric("Incomplete", total_incomplete)
        col4.metric("Files", total_files)
        
        st.markdown("---")
        
        rows = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            
            desc = p.get("description") or ""
            if isinstance(desc, dict):
                desc = desc.get("rendered", "") or desc.get("content", "")
            desc_preview = str(desc)[:50] + "..." if desc else ""
            
            meta = extract_meta_totals(p)
            
            rows.append({
                "ID": p.get("id"),
                "Title": extract_title(p),
                "Status": p.get("status") or "",
                "Tasks": str(meta.get("total_tasks", 0)),
                "Complete": str(meta.get("total_complete_tasks", 0)),
                "Files": meta.get("total_files", 0),
                "Created": p.get("created_at") or p.get("created") or "",
                "Description": desc_preview
            })
        
        df = pd.DataFrame(rows)
        st.dataframe(df, width='stretch', height=400)
        
        col1, col2 = st.columns(2)
        with col1:
            download_json(projects, "wp_projects.json", label="⬇️ Download Projects JSON")
        
        with col2:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Download Projects CSV",
                data=csv,
                file_name="wp_projects.csv",
                mime="text/csv"
            )

    # Project Management Section
    st.markdown("---")
    st.subheader("🛠️ Project Management")
    
    action_tabs = st.tabs(["✏️ Edit", "➕ Create", "📋 Clone", "📥 Import"])
    
    # EDIT TAB
    with action_tabs[0]:
        col1, col2 = st.columns([3, 1])
        with col1:
            project_id = st.text_input("Enter Project ID to Edit", key="edit_project_id")
        with col2:
            load_btn = st.button("📥 Load Project", width='stretch')
        
        if load_btn and project_id:
            with st.spinner("Loading project..."):
                proj = wp_get_json(f"{projects_url}/{project_id}")
                if proj:
                    # Handle nested data structure
                    if isinstance(proj, dict) and "data" in proj:
                        proj = proj["data"]
                    st.session_state["edit_project"] = proj
                    st.success("✅ Project loaded successfully.")
                    if show_raw_json:
                        with st.expander("Raw JSON"):
                            st.json(proj)

        edit_project = st.session_state.get("edit_project")
        if edit_project:
            with st.form("edit_project_form"):
                new_title = st.text_input("Title", extract_title(edit_project))
                new_status = st.selectbox("Status", ["incomplete", "active", "pending", "completed", "archived"], 
                                         index=["incomplete", "active", "pending", "completed", "archived"].index(edit_project.get("status", "incomplete")) if edit_project.get("status") in ["incomplete", "active", "pending", "completed", "archived"] else 0)
                
                desc_val = edit_project.get("description", "")
                if isinstance(desc_val, dict):
                    desc_val = desc_val.get("content", "") or desc_val.get("html", "")
                new_desc = st.text_area("Description", desc_val or "", height=150)
                
                col1, col2 = st.columns(2)
                with col1:
                    save_btn = st.form_submit_button("💾 Save Changes", width='stretch')
                with col2:
                    delete_btn = st.form_submit_button("🗑️ Delete Project", width='stretch')
                
                if save_btn:
                    payload = {"title": new_title, "status": new_status, "description": new_desc}
                    res = wp_put_json(f"{projects_url}/{edit_project.get('id')}", payload)
                    if res:
                        st.success("✅ Project updated successfully.")
                        st.session_state["edit_project"] = res
                        if show_raw_json:
                            st.json(res)
                
                if delete_btn:
                    if st.session_state.get("confirm_delete"):
                        res = wp_delete_json(f"{projects_url}/{edit_project.get('id')}")
                        if res:
                            st.success("✅ Project deleted successfully.")
                            st.session_state.pop("edit_project", None)
                            st.session_state.pop("confirm_delete", None)
                            st.rerun()
                    else:
                        st.session_state["confirm_delete"] = True
                        st.warning("⚠️ Click Delete again to confirm deletion.")
    
    # CREATE TAB
    with action_tabs[1]:
        with st.form("create_project_form"):
            st.write("Create a new project")
            create_title = st.text_input("Project Title", key="create_title")
            create_status = st.selectbox("Status", ["incomplete", "active", "pending", "completed"], key="create_status")
            create_desc = st.text_area("Description", key="create_desc", height=150)
            
            if st.form_submit_button("➕ Create Project", width='stretch'):
                if create_title:
                    payload = {
                        "title": create_title,
                        "status": create_status,
                        "description": create_desc
                    }
                    res = wp_post_json(projects_url, payload)
                    if res:
                        st.success(f"✅ Project created successfully! ID: {res.get('id') if isinstance(res, dict) else 'N/A'}")
                        if show_raw_json:
                            st.json(res)
                else:
                    st.error("Please enter a project title.")
    
    # CLONE TAB
    with action_tabs[2]:
        col1, col2 = st.columns([3, 1])
        with col1:
            clone_id = st.text_input("Enter Project ID to Clone", key="clone_id")
        with col2:
            clone_btn = st.button("📋 Clone", width='stretch')
        
        if clone_btn and clone_id:
            with st.spinner("Cloning project..."):
                proj = wp_get_json(f"{projects_url}/{clone_id}")
                if proj:
                    if isinstance(proj, dict) and "data" in proj:
                        proj = proj["data"]
                    
                    title = extract_title(proj)
                    desc = proj.get("description", "")
                    if isinstance(desc, dict):
                        desc = desc.get("content", "") or desc.get("html", "")
                    
                    clone_payload = {
                        "title": f"{title} (Copy)",
                        "status": proj.get("status", "incomplete"),
                        "description": desc
                    }
                    
                    res = wp_post_json(projects_url, clone_payload)
                    if res:
                        st.success(f"✅ Project cloned successfully! New ID: {res.get('id') if isinstance(res, dict) else 'N/A'}")
                        if show_raw_json:
                            st.json(res)
    
    # IMPORT TAB
    with action_tabs[3]:
        st.write("Import project from JSON file")
        uploaded_file = st.file_uploader("Choose a JSON file", type=['json'], key="import_json")
        
        if uploaded_file is not None:
            try:
                import_data = json.load(uploaded_file)
                st.json(import_data)
                
                if st.button("📥 Import Project", width='stretch'):
                    # Extract relevant fields
                    if isinstance(import_data, dict):
                        if "data" in import_data:
                            import_data = import_data["data"]
                        
                        payload = {
                            "title": extract_title(import_data),
                            "status": import_data.get("status", "incomplete"),
                            "description": import_data.get("description", "")
                        }
                        
                        res = wp_post_json(projects_url, payload)
                        if res:
                            st.success(f"✅ Project imported successfully! ID: {res.get('id') if isinstance(res, dict) else 'N/A'}")
                            if show_raw_json:
                                st.json(res)
                    else:
                        st.error("Invalid JSON format")
            except Exception as e:
                st.error(f"Error reading JSON: {e}")

# -------------------------------------
# TAB 2: TASKS & TASK LISTS
# -------------------------------------
with tab2:
    st.header("📋 Task Lists & Tasks Management")
    
    if not projects:
        st.info("👈 Please fetch projects first from the 'WP Projects' tab.")
    else:
        project_options = {f"{p.get('id')} - {extract_title(p)}": p.get('id') for p in projects}
        selected_project_label = st.selectbox("Select Project", options=list(project_options.keys()))
        selected_project_id = project_options[selected_project_label]
        
        # Show project stats
        selected_project = next((p for p in projects if p.get('id') == selected_project_id), None)
        if selected_project:
            meta = extract_meta_totals(selected_project)
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Task Lists", meta.get("total_task_lists", 0))
            col2.metric("Total Tasks", meta.get("total_tasks", 0))
            col3.metric("Complete", meta.get("total_complete_tasks", 0))
            col4.metric("Incomplete", meta.get("total_incomplete_tasks", 0))
            col5.metric("Files", meta.get("total_files", 0))
        
        st.markdown("---")
        


        # Automatically fetch task lists and tasks when a project is selected or tab is accessed
        if selected_project_id and (st.session_state.get("current_project_id") != selected_project_id or not st.session_state.get("current_task_lists") or not st.session_state.get("current_tasks")):
            with st.spinner(f"Fetching task data for project {selected_project_id}..."):
                task_lists, tasks = fetch_project_tasks(selected_project_id, projects_url, wp_base, api_ns, fetch_all_pages)
                st.session_state["current_task_lists"] = task_lists
                st.session_state["current_tasks"] = tasks
                st.session_state["current_project_id"] = selected_project_id
                
                if not task_lists and not tasks:
                    st.warning("No tasks or task lists found for this project, or permission denied.")
                else:
                    st.success(f"✅ Fetched {len(task_lists)} task lists and {len(tasks)} tasks for project {selected_project_id}.")
        
        # Allow manual refetch
        if st.button("🔄 Re-fetch Task Lists & Tasks", width='stretch'):
            with st.spinner(f"Re-fetching task data for project {selected_project_id}..."):
                task_lists, tasks = fetch_project_tasks(selected_project_id, projects_url, wp_base, api_ns, fetch_all_pages)
                st.session_state["current_task_lists"] = task_lists
                st.session_state["current_tasks"] = tasks
                st.session_state["current_project_id"] = selected_project_id
                
                if not task_lists and not tasks:
                    st.warning("No tasks or task lists found for this project, or permission denied.")
                else:
                    st.success(f"✅ Fetched {len(task_lists)} task lists and {len(tasks)} tasks for project {selected_project_id}.")
        
        task_lists = st.session_state.get("current_task_lists", [])
        tasks = st.session_state.get("current_tasks", [])
        
        if task_lists or tasks:
            download_col1, download_col2 = st.columns(2)
            with download_col1:
                if task_lists:
                    download_json(task_lists, f"project_{selected_project_id}_task_lists.json", label="⬇️ Download Task Lists JSON")
            with download_col2:
                if tasks:
                    download_json(tasks, f"project_{selected_project_id}_tasks.json", label="⬇️ Download Tasks JSON")
        
        if task_lists:
            st.subheader("📑 Task Lists")
            for tl in task_lists:
                if isinstance(tl, dict):
                    with st.expander(f"📑 {tl.get('title', 'Untitled')} (ID: {tl.get('id')})"):
                        st.write(f"**Description:** {tl.get('description', 'No description')}")
                        st.write(f"**Status:** {tl.get('status', 'N/A')}")
                        if show_raw_json:
                            st.json(tl)
        
        if tasks:
            st.subheader("✅ Tasks")
            task_rows = []
            for task in tasks:
                if isinstance(task, dict):
                    task_rows.append({
                        "ID": task.get("id"),
                        "Title": task.get("title", ""),
                        "Status": task.get("status", ""),
                        "Priority": task.get("priority", ""),
                        "Assignee": task.get("assignee", ""),
                        "Completed": task.get("completed", False)
                    })
            
        if task_rows:
            task_df = pd.DataFrame(task_rows)
            st.dataframe(task_df, width='stretch', height=400)

    # CSV Import Section
    st.markdown("---")
    st.subheader("📤 Import Tasks & Task Lists from CSV")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type=['csv'], key="import_tasks_csv")
    
    if uploaded_file is not None:
        try:
            # Read the CSV file
            df = pd.read_csv(uploaded_file)
            st.success(f"✅ CSV file loaded successfully! Found {len(df)} rows.")
            
            # Display preview of the data
            with st.expander("📋 Preview CSV Data"):
                st.dataframe(df.head(10), width='stretch')
            
            # Show statistics
            tasklist_count = len(df[df['type'] == 'tasklist'])
            task_count = len(df[df['type'] == 'task'])
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Task Lists", tasklist_count)
            col2.metric("Tasks", task_count)
            col3.metric("Total Rows", len(df))
            
            # Import options
            st.markdown("### Import Options")
            
            col1, col2 = st.columns(2)
            with col1:
                import_tasklists = st.checkbox("Import Task Lists", value=True)
                import_tasks = st.checkbox("Import Tasks", value=True)
            
            with col2:
                create_project_for_import = st.checkbox("Create new project for import", value=False)
                if create_project_for_import:
                    new_project_title = st.text_input("New Project Title", value="Imported Tasks Project")
            
            # Import button
            if st.button("🚀 Start Import Process", width='stretch'):
                if not (import_tasklists or import_tasks):
                    st.error("Please select at least one import option.")
                else:
                    # Create new project if requested
                    target_project_id = selected_project_id
                    if create_project_for_import:
                        with st.spinner("Creating new project..."):
                            project_payload = {
                                "title": new_project_title,
                                "status": "active",
                                "description": f"Project created for CSV import on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                            new_project = wp_post_json(projects_url, project_payload)
                            if new_project:
                                target_project_id = new_project.get('id')
                                st.success(f"✅ Created new project with ID: {target_project_id}")
                            else:
                                st.error("Failed to create new project.")
                                st.stop()
                    
                    if not target_project_id:
                        st.error("Please select a project or create a new one.")
                        st.stop()
                    
                    # Import process
                    import_results = {"tasklists": [], "tasks": [], "errors": []}
                    
                    # Step 1: Import Task Lists
                    if import_tasklists:
                        st.markdown("#### 📑 Importing Task Lists...")
                        tasklist_df = df[df['type'] == 'tasklist'].copy()
                        tasklist_mapping = {}  # Map original names to created IDs
                        
                        progress_bar = st.progress(0)
                        for idx, row in tasklist_df.iterrows():
                            try:
                                tasklist_payload = {
                                    "title": row['title'],
                                    "description": row.get('description', ''),
                                    "project_id": target_project_id,
                                    "order": row.get('order', 1),
                                    "status": row.get('status', 'incomplete')
                                }
                                
                                # Create task list via API
                                result = wp_post_json(f"{projects_url}/{target_project_id}/task-lists", tasklist_payload)
                                if result:
                                    tasklist_id = result.get('id')
                                    tasklist_mapping[row['title']] = tasklist_id
                                    import_results["tasklists"].append({
                                        "title": row['title'],
                                        "id": tasklist_id,
                                        "status": "success"
                                    })
                                    st.success(f"✅ Created task list: {row['title']} (ID: {tasklist_id})")
                                else:
                                    import_results["errors"].append(f"Failed to create task list: {row['title']}")
                                    st.error(f"❌ Failed to create task list: {row['title']}")
                                
                                progress_bar.progress((idx + 1) / len(tasklist_df))
                                time.sleep(0.1)  # Rate limiting
                                
                            except Exception as e:
                                error_msg = f"Error creating task list '{row['title']}': {str(e)}"
                                import_results["errors"].append(error_msg)
                                st.error(f"❌ {error_msg}")
                        
                        progress_bar.empty()
                    
                    # Step 2: Import Tasks
                    if import_tasks:
                        st.markdown("#### ✅ Importing Tasks...")
                        task_df = df[df['type'] == 'task'].copy()
                        
                        progress_bar = st.progress(0)
                        for idx, row in task_df.iterrows():
                            try:
                                # Find the task list ID
                                task_list_name = row.get('task_list_name', '')
                                task_list_id = tasklist_mapping.get(task_list_name)
                                
                                if not task_list_id and task_list_name:
                                    # Try to find existing task list by name
                                    existing_tasklists = fetch_all_pages(f"{projects_url}/{target_project_id}/task-lists")
                                    for tl in existing_tasklists:
                                        if tl.get('title') == task_list_name:
                                            task_list_id = tl.get('id')
                                            break
                                
                                task_payload = {
                                    "title": row['title'],
                                    "description": row.get('description', ''),
                                    "project_id": target_project_id,
                                    "order": row.get('order', 1),
                                    "status": row.get('status', 'incomplete'),
                                    "complexity": row.get('complexity', 'basic'),
                                    "priority": row.get('priority', 'medium')
                                }
                                
                                if task_list_id:
                                    task_payload["task_list_id"] = task_list_id
                                # Handle dates if present, converting NaN or empty strings to None
                                start_at_val = row.get(\'start_at\')
                                if pd.isna(start_at_val) or start_at_val in [\'\', "{\'date\': None, \'time\': None, \'datetime\': None, \'timezone\': \'Etc/UTC\', \'timestamp\': None}"]:
                                    task_payload["start_at"] = None
                                else:
                                    task_payload["start_at"] = start_at_val
                                
                                due_date_val = row.get(\'due_date\')
                                if pd.isna(due_date_val) or due_date_val in [\'\', "{\'date\': None, \'time\': None, \'datetime\': None, \'timezone\': \'Etc/UTC\', \'timestamp\': None}"]:
                                    task_payload["due_date"] = None
                                else:
                                    task_payload["due_date"] = due_date_val
                                # Create task via API
                                result = wp_post_json(f"{projects_url}/{target_project_id}/tasks", task_payload)
                                if result:
                                    task_id = result.get('id')
                                    import_results["tasks"].append({
                                        "title": row['title'],
                                        "id": task_id,
                                        "task_list": task_list_name,
                                        "status": "success"
                                    })
                                    st.success(f"✅ Created task: {row['title']} (ID: {task_id})")
                                else:
                                    import_results["errors"].append(f"Failed to create task: {row['title']}")
                                    st.error(f"❌ Failed to create task: {row['title']}")
                                
                                progress_bar.progress((idx + 1) / len(task_df))
                                time.sleep(0.1)  # Rate limiting
                                
                            except Exception as e:
                                error_msg = f"Error creating task '{row['title']}': {str(e)}"
                                import_results["errors"].append(error_msg)
                                st.error(f"❌ {error_msg}")
                        
                        progress_bar.empty()
                    
                    # Import Summary
                    st.markdown("---")
                    st.markdown("### 📊 Import Summary")
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Task Lists Created", len(import_results["tasklists"]))
                    col2.metric("Tasks Created", len(import_results["tasks"]))
                    col3.metric("Errors", len(import_results["errors"]))
                    
                    # Show errors if any
                    if import_results["errors"]:
                        with st.expander("❌ View Errors"):
                            for error in import_results["errors"]:
                                st.error(error)
                    
                    # Download import results
                    if import_results["tasklists"] or import_results["tasks"]:
                        download_json(import_results, "import_results.json", label="⬇️ Download Import Results")
                        
                        if target_project_id:
                            st.info(f"💡 Import completed for project ID: {target_project_id}. You can now view the imported data by selecting this project.")
        
        except Exception as e:
            st.error(f"Error reading CSV file: {str(e)}")

# -------------------------------------
# TAB 3: CUSTOM POST TYPES
# -------------------------------------
with tab3:
    st.header("🧱 Custom Post Types")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("🔄 Fetch All Post Types", width='stretch'):
            with st.spinner("Fetching post types..."):
                types = wp_get_json(f"{wp_base}/wp-json/wp/v2/types")
                if types:
                    st.session_state["post_types"] = types
                    st.success(f"✅ Found {len(types)} post types.")
                    if show_raw_json:
                        with st.expander("Raw JSON"):
                            st.json(types)

    post_types = st.session_state.get("post_types", {})
    
    if post_types:
        type_selected = st.selectbox("Select a post type", options=list(post_types.keys()))
        
        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button(f"🔄 Fetch '{type_selected}' Posts", width='stretch'):
                with st.spinner(f"Fetching {type_selected} posts..."):
                    posts = fetch_all_pages(f"{posts_url}/{type_selected}")
                    st.session_state["posts_data"] = posts
                    st.success(f"✅ Fetched {len(posts)} posts.")
        
        posts_data = st.session_state.get("posts_data", [])
        if posts_data:
            st.subheader(f"📊 {type_selected.title()} Posts ({len(posts_data)} total)")
            
            df = pd.DataFrame([
                {
                    "ID": p.get("id"),
                    "Title": extract_title(p),
                    "Status": p.get("status") or "",
                    "Date": p.get("date", "")[:10] if p.get("date") else "",
                    "Author": p.get("author", "")
                }
                for p in posts_data
            ])
            st.dataframe(df, width='stretch', height=400)
            
            col1, col2 = st.columns(2)
            with col1:
                download_json(posts_data, f"{type_selected}_export.json", label="⬇️ Download Posts JSON")
            with col2:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Posts CSV",
                    data=csv,
                    file_name=f"{type_selected}_export.csv",
                    mime="text/csv"
                )

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
