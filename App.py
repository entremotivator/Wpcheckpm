
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
                    error_msg += f"\n{error_data.get("message", res.text)}"
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
            st.error(f"POST failed: {error_data.get("message", str(e))}")
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
            st.error(f"PUT failed: {error_data.get("message", str(e))}")
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
        meta = project.get("meta", {})
        if isinstance(meta, dict):
            data = meta.get("data", {})
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
            elif "data" in data and isinstance(data["data"], dict):
                all_items.append(data["data"])
                break
            else:
                break
        else:
            break
            
        page += 1
        time.sleep(0.1)
    
    return all_items

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
        
        # Show aggregate stats
        total_tasks = 0
        total_complete = 0
        total_incomplete = 0
        total_files = 0
        
        for p in projects:
            meta = extract_meta_totals(p)
            total_tasks += meta.get("total_tasks", 0)
            total_complete += meta.get("total_complete_tasks", 0)
            total_incomplete += meta.get("total_incomplete_tasks", 0)
            total_files += meta.get("total_files", 0)
        
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
                "Tasks": meta.get("total_tasks", 0),
                "Complete": meta.get("total_complete_tasks", 0),
                "Files": meta.get("total_files", 0),
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
            load_btn = st.button("📥 Load Project", use_container_width=True)
        
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
                    save_btn = st.form_submit_button("💾 Save Changes", use_container_width=True)
                with col2:
                    delete_btn = st.form_submit_button("🗑️ Delete Project", use_container_width=True)
                
                if save_btn:
                    payload = {"title": new_title, "status": new_status, "description": new_desc}
                    res = wp_put_json(f"{projects_url}/{edit_project.get("id")}", payload)
                    if res:
                        st.success("✅ Project updated successfully.")
                        st.session_state["edit_project"] = res
                        if show_raw_json:
                            st.json(res)
                
                if delete_btn:
                    if st.session_state.get("confirm_delete"):
                        res = wp_delete_json(f"{projects_url}/{edit_project.get("id")}")
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
            
            if st.form_submit_button("➕ Create Project", use_container_width=True):
                if create_title:
                    payload = {
                        "title": create_title,
                        "status": create_status,
                        "description": create_desc
                    }
                    res = wp_post_json(projects_url, payload)
                    if res:
                        st.success(f"✅ Project created successfully! ID: {res.get("id") if isinstance(res, dict) else "N/A"}")
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
            clone_btn = st.button("📋 Clone", use_container_width=True)
        
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
                        st.success(f"✅ Project cloned successfully! New ID: {res.get("id") if isinstance(res, dict) else "N/A"}")
                        if show_raw_json:
                            st.json(res)
    
    # IMPORT TAB
    with action_tabs[3]:
        st.write("Import project from JSON file")
        uploaded_file = st.file_uploader("Choose a JSON file", type=["json"], key="import_json")
        
        if uploaded_file is not None:
            try:
                import_data = json.load(uploaded_file)
                st.json(import_data)
                
                if st.button("📥 Import Project", use_container_width=True):
                    # Extract relevant fields
                    if isinstance(import_data, dict):
                        title = import_data.get("title", "Imported Project")
                        status = import_data.get("status", "incomplete")
                        description = import_data.get("description", "")
                        if isinstance(description, dict):
                            description = description.get("content", "") or description.get("html", "")

                        payload = {
                            "title": title,
                            "status": status,
                            "description": description
                        }
                        res = wp_post_json(projects_url, payload)
                        if res:
                            st.success(f"✅ Project imported successfully! ID: {res.get("id") if isinstance(res, dict) else "N/A"}")
                            if show_raw_json:
                                st.json(res)
                    else:
                        st.error("Invalid JSON format for project import.")
            except Exception as e:
                st.error(f"Error parsing JSON file: {e}")

# -------------------------------------
# TAB 2: TASKS & LISTS
# -------------------------------------
with tab2:
    st.header("📋 Tasks & Lists")
    
    if not projects:
        st.info("👈 Please fetch projects first from the 'WP Projects' tab.")
    else:
        project_options = {f"{p.get("id")} - {extract_title(p)}": p.get("id") for p in projects}
        selected_project_label = st.selectbox("Select Project", options=list(project_options.keys()))
        selected_project_id = project_options[selected_project_label]
        
        # Show project stats
        selected_project = next((p for p in projects if p.get("id") == selected_project_id), None)
        if selected_project:
            meta = extract_meta_totals(selected_project)
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Task Lists", meta.get("total_task_lists", 0))
            col2.metric("Total Tasks", meta.get("total_tasks", 0))
            col3.metric("Complete", meta.get("total_complete_tasks", 0))
            col4.metric("Incomplete", meta.get("total_incomplete_tasks", 0))
            col5.metric("Files", meta.get("total_files", 0))
        
        st.markdown("---")
        
        if st.button("🔄 Fetch Task Lists & Tasks", use_container_width=True):
            with st.spinner("Fetching task data..."):
                task_lists = fetch_all_pages(f"{projects_url}/{selected_project_id}/task-lists")
                tasks = fetch_all_pages(f"{projects_url}/{selected_project_id}/tasks")
                
                if task_lists or tasks:
                    st.session_state["current_task_lists"] = task_lists or []
                    st.session_state["current_tasks"] = tasks or []
                    st.session_state["current_project_id"] = selected_project_id
                    st.success(f"✅ Fetched {len(task_lists or [])} task lists and {len(tasks or [])} tasks.")
                else:
                    st.warning("No tasks or task lists found, or permission denied.")
        
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
                    with st.expander(f"📑 {tl.get("title", "Untitled")} (ID: {tl.get("id")})"):
                        st.write(f"**Description:** {tl.get("description", "N/A")}")
                        st.write(f"**Status:** {tl.get("status", "N/A")}")
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
                st.dataframe(task_df, use_container_width=True, height=400)

# -------------------------------------
# TAB 3: CUSTOM POST TYPES
# -------------------------------------
with tab3:
    st.header("🧱 Custom Post Types")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("🔄 Fetch All Post Types", use_container_width=True):
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
            if st.button(f"🔄 Fetch \'{type_selected}\' Posts", use_container_width=True):
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
            st.dataframe(df, use_container_width=True, height=400)
            
            col1, col2 = st.columns(2)
            with col1:
                download_json(posts_data, f"{type_selected}_export.json", label="⬇️ Download Posts JSON")
            with col2:
                csv = df.to_csv(index=False).encode("utf-8")
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

