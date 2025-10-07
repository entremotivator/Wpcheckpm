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
from typing import Dict, Any

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
include_tasks = st.sidebar.checkbox("Include Task Lists & Tasks (slow)", value=True)

# API URLs
projects_url = f"{wp_base}/wp-json/{api_ns}/projects"
posts_url = f"{wp_base}/wp-json/wp/v2"

st.title("🧩 WP Project Manager + Custom Post Explorer")
st.caption("Fetch, export, import, and edit WordPress Project Manager data and all custom post types using REST API + App Password authentication.")

# -------------------------------------
# Helper functions
# -------------------------------------
def wp_get_json(url: str, params: Dict[str, Any] = None):
    try:
        res = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
        res.raise_for_status()
        return res.json()
    except requests.HTTPError as e:
        st.error(f"HTTP Error: {e}\nResponse: {res.text}")
        return None
    except Exception as e:
        st.error(f"Error connecting to {url}: {e}")
        return None

def wp_post_json(url: str, data: Dict[str, Any]):
    try:
        res = requests.post(url, headers=headers, auth=auth, json=data, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"POST failed: {e}")
        return None

def wp_put_json(url: str, data: Dict[str, Any]):
    try:
        res = requests.put(url, headers=headers, auth=auth, json=data, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        st.error(f"PUT failed: {e}")
        return None

def download_json(obj, filename: str, label="Download JSON"):
    b = json.dumps(obj, indent=2).encode("utf-8")
    st.download_button(label=label, data=b, file_name=filename, mime="application/json")

def extract_title(p: dict) -> str:
    """
    Safely extract the title from WP REST API project or CPT object.
    Handles title as dict (with 'rendered') or string, plus fallback keys.
    """
    t = p.get("title")
    if isinstance(t, dict):
        return t.get("rendered", "")
    elif isinstance(t, str):
        return t
    return p.get("project_title") or p.get("name") or ""

# -------------------------------------
# Tabs
# -------------------------------------
tab1, tab2, tab3 = st.tabs(["📁 WP Projects", "🧱 Custom Post Types", "🗄️ DB Export/Import"])

# -------------------------------------
# TAB 1: WP PROJECT MANAGER
# -------------------------------------
with tab1:
    st.header("📁 WP Project Manager Projects")
    
    if st.button("Fetch Projects"):
        with st.spinner("Fetching projects..."):
            all_projects = []
            page = 1
            while True:
                data = wp_get_json(projects_url, params={"per_page": 50, "page": page})
                if not data:
                    break
                if isinstance(data, list):
                    all_projects.extend([p for p in data if isinstance(p, dict)])
                elif isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    all_projects.extend([p for p in data["data"] if isinstance(p, dict)])
                else:
                    break
                if len(data) < 50:
                    break
                page += 1
                time.sleep(0.1)
            st.session_state["projects"] = all_projects
            st.success(f"Fetched {len(all_projects)} projects.")

    projects = st.session_state.get("projects", [])
    if projects:
        rows = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            rows.append({
                "ID": p.get("id"),
                "Title": extract_title(p),
                "Status": p.get("status") or "",
                "Created": p.get("created_at") or p.get("created") or ""
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        
        if st.button("Download Projects JSON"):
            download_json(projects, "wp_projects.json")

        if include_tasks:
            st.info("Fetching task-lists & tasks for each project...")
            for p in projects:
                pid = p.get("id")
                if pid:
                    p["task_lists"] = wp_get_json(f"{projects_url}/{pid}/task-lists") or []
                    p["tasks"] = wp_get_json(f"{projects_url}/{pid}/tasks") or []

    # Edit project
    st.subheader("✏️ Edit Project")
    project_id = st.text_input("Enter Project ID to Edit")
    if st.button("Load Project"):
        if project_id:
            proj = wp_get_json(f"{projects_url}/{project_id}")
            if proj:
                st.session_state["edit_project"] = proj
                st.success("Project loaded successfully.")

    edit_project = st.session_state.get("edit_project")
    if edit_project:
        new_title = st.text_input("Title", extract_title(edit_project))
        new_status = st.text_input("Status", edit_project.get("status") or "")
        new_desc = st.text_area("Description", edit_project.get("description") or "")
        if st.button("Save Changes"):
            payload = {"title": new_title, "status": new_status, "content": new_desc}
            res = wp_put_json(f"{projects_url}/{edit_project.get('id')}", payload)
            if res:
                st.success("✅ Project updated successfully.")
                st.json(res)

# -------------------------------------
# TAB 2: CUSTOM POST TYPES
# -------------------------------------
with tab2:
    st.header("🧱 Custom Post Types")
    
    if st.button("Fetch All Post Types"):
        types = wp_get_json(f"{wp_base}/wp-json/wp/v2/types")
        if types:
            st.session_state["post_types"] = types
            st.json(types)
            st.success(f"Found {len(types)} post types.")

    post_types = st.session_state.get("post_types", {})
    if post_types:
        type_selected = st.selectbox("Select a post type", options=list(post_types.keys()))
        if st.button("Fetch Posts of this Type"):
            posts = wp_get_json(f"{posts_url}/{type_selected}", params={"per_page": 50})
            if posts:
                posts_list = [p for p in posts if isinstance(p, dict)]
                st.session_state["posts_data"] = posts_list
                st.success(f"Fetched {len(posts_list)} posts.")
        posts_data = st.session_state.get("posts_data", [])
        if posts_data:
            df = pd.DataFrame([
                {
                    "ID": p.get("id"),
                    "Title": extract_title(p),
                    "Status": p.get("status") or ""
                }
                for p in posts_data
            ])
            st.dataframe(df, use_container_width=True)
            download_json(posts_data, f"{type_selected}_export.json", label="Download Posts JSON")

# -------------------------------------
# TAB 3: DB EXPORT/IMPORT
# -------------------------------------
with tab3:
    st.header("🗄️ Database Export / Import (Advanced)")
    
    if not HAS_PYMYSQL:
        st.warning("Install `pymysql` to enable DB features: `pip install pymysql`")
    else:
        db_host = st.text_input("DB Host", "localhost")
        db_user = st.text_input("DB User", "root")
        db_password = st.text_input("DB Password", type="password")
        db_name = st.text_input("Database Name", "wordpress")
        db_port = st.number_input("DB Port", 3306)

        if st.button("Test DB Connection"):
            try:
                con = pymysql.connect(
                    host=db_host, user=db_user, password=db_password,
                    db=db_name, port=int(db_port), connect_timeout=5
                )
                st.success("✅ Connected successfully!")
                con.close()
            except Exception as e:
                st.error(f"Connection failed: {e}")

# -------------------------------------
# Footer
# -------------------------------------
st.markdown("---")
st.caption("Developed for WordPress REST API exploration — supports WP Project Manager and all custom post types. Handles App Password authentication safely.")
