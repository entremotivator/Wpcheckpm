"""
Streamlit app: WP Project Manager - Export / Import / Edit Projects

Usage:
    pip install -r requirements.txt
    streamlit run app.py

requirements.txt:
    streamlit
    requests
    pandas
    pymysql   # only needed for DB import/export
"""

import streamlit as st
import requests
import json
import pandas as pd
from typing import Optional, List, Dict, Any
from io import BytesIO
import base64
import time

# Optional DB
try:
    import pymysql
    HAS_PYMYSQL = True
except Exception:
    HAS_PYMYSQL = False

st.set_page_config(page_title="WP Project Manager - Export/Import/Edit", layout="wide")

# -----------------------
# Helper functions
# -----------------------
def build_auth_headers(auth_type: str, username: str, password: str, token: str):
    headers = {"Accept": "application/json"}
    if auth_type == "basic":
        # Basic auth via requests (we'll return None for headers and use auth param)
        return headers, (username, password)
    elif auth_type == "bearer":
        headers["Authorization"] = f"Bearer {token}"
        return headers, None
    elif auth_type == "none":
        return headers, None
    else:
        return headers, None

def get_json(url: str, headers: dict = None, auth=None, params: dict = None, timeout=30):
    try:
        r = requests.get(url, headers=headers, auth=auth, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"HTTP Error: {e} - {r.text if 'r' in locals() else ''}")
        return None
    except Exception as e:
        st.error(f"Error requesting {url}: {e}")
        return None

def post_json(url: str, data: dict, headers: dict = None, auth=None):
    try:
        r = requests.post(url, headers=headers, json=data, auth=auth)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"HTTP Error POST: {e} - {r.text if 'r' in locals() else ''}")
        return None
    except Exception as e:
        st.error(f"Error POSTing to {url}: {e}")
        return None

def put_json(url: str, data: dict, headers: dict = None, auth=None):
    try:
        r = requests.put(url, headers=headers, json=data, auth=auth)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.error(f"HTTP Error PUT: {e} - {r.text if 'r' in locals() else ''}")
        return None
    except Exception as e:
        st.error(f"Error PUT to {url}: {e}")
        return None

def download_button(obj, filename: str, label: str = "Download"):
    b = json.dumps(obj, indent=2).encode("utf-8")
    st.download_button(label=label, data=b, file_name=filename, mime="application/json")

# -----------------------
# UI: Sidebar - Connection
# -----------------------
st.sidebar.title("Connection & Settings")

wp_base = st.sidebar.text_input("WP Site base URL", value="https://videmiservices.com", help="Enter base site URL (no trailing slash). Example: https://example.com")
if wp_base.endswith("/"):
    wp_base = wp_base[:-1]

auth_method = st.sidebar.selectbox("Auth method", options=["none", "basic", "bearer"], index=0)
username = st.sidebar.text_input("WP username (for basic auth)", value="", help="If using basic auth provide username")
password = st.sidebar.text_input("WP password (for basic auth)", type="password")
bearer_token = st.sidebar.text_input("Bearer/JWT token (for token auth)", type="password")

# API namespace and endpoints (defaults for WP Project Manager)
api_ns = st.sidebar.text_input("API namespace", value="pm/v2", help="REST namespace for WP Project Manager (default pm/v2)")
projects_endpoint = f"{wp_base}/wp-json/{api_ns}/projects"

st.sidebar.markdown("**Options**")
use_db = st.sidebar.checkbox("Enable MySQL DB import/export (advanced)", value=False)
if use_db and not HAS_PYMYSQL:
    st.sidebar.warning("pymysql not installed — DB features disabled. `pip install pymysql`")

# Build headers/auth for requests
headers, auth = build_auth_headers(auth_method, username, password, bearer_token)

st.title("WP Project Manager — Export / Import / Edit")
st.write("Connect to WP site and manage projects via REST API or database. Use with care.")

# -----------------------
# Main tabs
# -----------------------
tabs = st.tabs(["List & Export", "Import", "Edit Project", "DB Export/Import (advanced)"])

# -----------------------
# TAB 1: List & Export
# -----------------------
with tabs[0]:
    st.header("List projects (API)")
    if st.button("Fetch projects from API"):
        if not wp_base:
            st.error("Please enter WP site base URL in sidebar.")
        else:
            with st.spinner("Fetching projects..."):
                params = {"per_page": 50, "page": 1}
                all_projects = []
                while True:
                    res = get_json(projects_endpoint, headers=headers, auth=auth, params=params)
                    if not res:
                        break
                    # if response is a dict with data key or list; handle both
                    if isinstance(res, dict) and "data" in res and isinstance(res["data"], list):
                        chunk = res["data"]
                    elif isinstance(res, list):
                        chunk = res
                    else:
                        # sometimes API returns object with projects keyed differently
                        chunk = res if isinstance(res, list) else []
                    if not chunk:
                        break
                    all_projects.extend(chunk)
                    if len(chunk) < params["per_page"]:
                        break
                    params["page"] += 1
                    time.sleep(0.2)
                st.session_state["projects_raw"] = all_projects
                st.success(f"Fetched {len(all_projects)} projects.")
    projects_raw = st.session_state.get("projects_raw", None)
    if projects_raw:
        st.subheader("Projects table")
        # show summary table
        rows = []
        for p in projects_raw:
            rows.append({
                "id": p.get("id"),
                "title": p.get("title") or p.get("project_title") or p.get("name"),
                "status": p.get("status"),
                "created_at": p.get("created_at") or p.get("created"),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df)

        st.markdown("**Export options**")
        sel = st.multiselect("Select project IDs to export (empty → export all)", options=[r["id"] for r in rows])
        if st.button("Prepare export JSON"):
            if sel:
                export_list = [p for p in projects_raw if p.get("id") in sel]
            else:
                export_list = projects_raw
            # Optionally fetch tasks and files per project
            if st.checkbox("Include task-lists & tasks (slow)", value=True):
                for p in export_list:
                    pid = p.get("id")
                    if pid is None:
                        continue
                    tl_url = f"{projects_endpoint}/{pid}/task-lists"
                    t_url = f"{projects_endpoint}/{pid}/tasks"
                    fl_url = f"{projects_endpoint}/{pid}/files"
                    p["task_lists"] = get_json(tl_url, headers=headers, auth=auth) or []
                    p["tasks"] = get_json(t_url, headers=headers, auth=auth) or []
                    p["files"] = get_json(fl_url, headers=headers, auth=auth) or []
            st.session_state["export_payload"] = export_list
            st.success(f"Prepared {len(export_list)} projects for export.")
        export_payload = st.session_state.get("export_payload", None)
        if export_payload:
            download_button(export_payload, filename="pm_projects_export.json", label="Download projects JSON")

# -----------------------
# TAB 2: Import
# -----------------------
with tabs[1]:
    st.header("Import projects (API)")
    st.write("Upload JSON exported by this app or compatible JSON. This will attempt to create projects via API.")
    uploaded = st.file_uploader("Upload projects JSON file", type=["json"])
    create_options = st.radio("When creating projects", options=["Create new projects", "Skip existing (by id)"], index=0)
    if uploaded:
        try:
            payload = json.load(uploaded)
            st.write(f"Loaded {len(payload)} top-level items.")
            if st.button("Preview payload"):
                st.json(payload[:3])
            if st.button("Import via API now"):
                created = []
                failed = []
                for p in payload:
                    # Prepare minimal create payload — adapt depending on your plugin expects
                    create_payload = {
                        "title": p.get("title") or p.get("name") or p.get("project_title"),
                        "content": p.get("description") or p.get("content") or "",
                        "status": p.get("status") or "open"
                    }
                    # If plugin supports POST /projects
                    res = post_json(projects_endpoint, create_payload, headers=headers, auth=auth)
                    if res:
                        created.append(res)
                        # Optionally create task lists / tasks
                        pid = res.get("id")
                        # create task lists
                        for tl in (p.get("task_lists") or []):
                            tl_payload = {"title": tl.get("title") or tl.get("name"), "project_id": pid}
                            post_json(f"{projects_endpoint}/{pid}/task-lists", tl_payload, headers=headers, auth=auth)
                        # create tasks
                        for t in (p.get("tasks") or []):
                            t_payload = {
                                "project_id": pid,
                                "title": t.get("title") or t.get("name"),
                                "description": t.get("description") or t.get("content") or ""
                            }
                            post_json(f"{projects_endpoint}/{pid}/tasks", t_payload, headers=headers, auth=auth)
                    else:
                        failed.append(p)
                st.success(f"Created {len(created)} projects; failed {len(failed)}")
                if created:
                    st.write("Created projects (top 5):")
                    st.json(created[:5])
        except Exception as e:
            st.error(f"Invalid JSON: {e}")

# -----------------------
# TAB 3: Edit Project
# -----------------------
with tabs[2]:
    st.header("Edit a project (API)")
    pid_to_edit = st.text_input("Project ID to load for editing", value="")
    if st.button("Load project"):
        if not pid_to_edit:
            st.error("Enter project ID.")
        else:
            p = get_json(f"{projects_endpoint}/{pid_to_edit}", headers=headers, auth=auth)
            if p:
                st.session_state["editing_project"] = p
                st.success("Loaded project.")
    editing_project = st.session_state.get("editing_project", None)
    if editing_project:
        st.subheader(f"Editing project ID {editing_project.get('id')}")
        # Pick editable fields
        title = st.text_input("Title", value=editing_project.get("title") or editing_project.get("project_title") or "")
        status = st.text_input("Status", value=editing_project.get("status") or "")
        content = st.text_area("Content / Description", value=editing_project.get("description") or editing_project.get("content") or "")
        if st.button("Submit update"):
            update_payload = {"title": title, "status": status, "content": content}
            res = put_json(f"{projects_endpoint}/{editing_project.get('id')}", update_payload, headers=headers, auth=auth)
            if res:
                st.success("Project updated.")
                st.session_state["editing_project"] = res

# -----------------------
# TAB 4: DB Export/Import (advanced)
# -----------------------
with tabs[3]:
    st.header("DB Export / Import (Advanced)")
    st.write("Use this if REST API is missing data. This connects to MySQL and can export/import plugin tables. Use carefully.")
    if not HAS_PYMYSQL:
        st.warning("pymysql is not installed on this environment; DB features disabled. To enable, `pip install pymysql` and restart.")
    st.markdown("**Export plugin tables**")
    db_host = st.text_input("DB host", value="localhost")
    db_port = st.text_input("DB port", value="3306")
    db_user = st.text_input("DB user", value="root")
    db_password = st.text_input("DB password", type="password")
    db_name = st.text_input("DB name", value="wordpress")
    table_prefix = st.text_input("WP table prefix", value="wp_")
    plugin_table_names = st.text_area("Plugin table suffixes (comma-separated)", value="pm_projects,pm_tasks,pm_task_lists,pm_files", help="Example: pm_projects,pm_tasks")
    if st.button("Export selected plugin tables to SQL"):
        if not HAS_PYMYSQL:
            st.error("pymysql not available.")
        else:
            try:
                con = pymysql.connect(host=db_host, port=int(db_port), user=db_user, password=db_password, db=db_name, charset='utf8mb4')
                cur = con.cursor()
                suffixes = [s.strip() for s in plugin_table_names.split(",") if s.strip()]
                combined_sql = ""
                for s in suffixes:
                    tbl = table_prefix + s
                    # fetch create statement
                    cur.execute(f"SHOW CREATE TABLE `{tbl}`")
                    row = cur.fetchone()
                    if not row:
                        st.warning(f"No table {tbl}")
                        continue
                    create_stmt = row[1] + ";\n\n"
                    combined_sql += create_stmt
                    # fetch rows
                    cur.execute(f"SELECT * FROM `{tbl}`")
                    rows = cur.fetchall()
                    cols = [desc[0] for desc in cur.description]
                    for r in rows:
                        vals = []
                        for v in r:
                            if v is None:
                                vals.append("NULL")
                            else:
                                vals.append("'" + pymysql.converters.escape_string(str(v)) + "'")
                        combined_sql += f"INSERT INTO `{tbl}` (`{'`,`'.join(cols)}`) VALUES ({', '.join(vals)});\n"
                    combined_sql += "\n"
                if combined_sql:
                    st.download_button("Download SQL dump", data=combined_sql.encode("utf-8"), file_name="pm_tables_dump.sql", mime="text/sql")
                else:
                    st.info("No SQL generated.")
                cur.close()
                con.close()
            except Exception as e:
                st.error(f"DB error: {e}")

    st.markdown("---")
    st.markdown("**Import SQL (be careful)**")
    sql_file = st.file_uploader("Upload SQL file to import into DB", type=["sql", "txt"])
    if sql_file and st.button("Import SQL into DB now"):
        if not HAS_PYMYSQL:
            st.error("pymysql not installed.")
        else:
            try:
                sql_content = sql_file.read().decode("utf-8")
                con = pymysql.connect(host=db_host, port=int(db_port), user=db_user, password=db_password, db=db_name, charset='utf8mb4', autocommit=True)
                cur = con.cursor()
                # naive split by semicolon — for production use proper sql parsing
                statements = [s.strip() for s in sql_content.split(";") if s.strip()]
                for s in statements:
                    try:
                        cur.execute(s)
                    except Exception as ex:
                        st.warning(f"Failed statement (continuing): {ex}")
                st.success("SQL import attempted (check DB for results).")
                cur.close()
                con.close()
            except Exception as e:
                st.error(f"Error importing SQL: {e}")

# -----------------------
# Footer notes
# -----------------------
st.markdown("---")
st.write("Notes: If API endpoints differ, adjust the `api namespace` in the sidebar. For cookie/nonce-based WP auth you may need to fetch wp-nonce and include it in headers. This app is a starting point — adapt payload shapes to match the plugin version you run.")
