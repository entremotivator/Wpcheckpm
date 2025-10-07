# Import section (only once!)
        st.markdown("---")
        st.subheader("⬆️ Import Task Data")
        
        col1, col2 = st.columns(2)
        with col1:
            uploaded_file = st.file_uploader("Upload JSON or CSV file", type=["json", "csv"], key=f"upload_task_data_{selected_project_id}")
        with col2:
            import_type = st.radio("Import as:", ["Task Lists", "Tasks"], key=f"import_type_{selected_project_id}")
        
        if uploaded_file is not None:
            file_extension = uploaded_file.name.split(".")[-1].lower()
            
            # Parse file based on type
            if file_extension == "json":
                import_data = json.load(uploaded_file)
                if isinstance(import_data, dict):
                    import_data = [import_data]
            else:  # CSV
                df_import = pd.read_csv(uploaded_file)
                # Convert DataFrame to list of dicts
                import_data = df_import.to_dict('records')
            
            st.write(f"Preview of uploaded data ({len(import_data)} items):")
            st.dataframe(pd.DataFrame(import_data).head(10), use_container_width=True)
            
            st.info("💡 Note: Only POST (create new) is supported. Update via PUT may not be available for all endpoints.")
            
            if st.button("⬆️ Import Data", use_container_width=True, key=f"process_upload_btn_{selected_project_id}"):
                imported_count = 0
                failed_count = 0
                
                if import_type == "Task Lists":
                    endpoint = f"{projects_url}/{selected_project_id}/task-lists"
                    item_type = "Task List"
                else:
                    endpoint = f"{projects_url}/{selected_project_id}/tasks"
                    item_type = "Task"
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for index, item in enumerate(import_data):
                    status_text.text(f"Processing {index + 1}/{len(import_data)}...")
                    
                    # Clean the payload
                    payload = {}
                    for k, v in item.items():
                        # Skip ID field to create new items
                        if k.lower() in ['id']:
                            continue
                        # Handle NaN and None values
                        if pd.isna(v) if isinstance(v, float) else v is None:
                            continue
                        # Convert numpy types to Python types
                        if hasattr(v, 'item'):
                            v = v.item()
                        payload[k] = v
                    
                    # Try to create new item
                    res = wp_post_json(endpoint, payload)
                    if res:
                        imported_count += 1
                    else:
                        failed_count += 1
                    
                    progress_bar.progress((index + 1) / len(import_data))
                    time.sleep(0.15)  # Be kind to the API
                
                progress_bar.empty()
                status_text.empty()
                
                if imported_count > 0:
                    st.success(f"✅ Successfully imported {imported_count} {item_type}(s).")
                if failed_count > 0:
                    st.error(f"❌ Failed to import {failed_count} {item_type}(s). Check error messages above.")
                
                if imported_count > 0:
                    st.info("✨ Import completed! Re-fetching data...")
                    # Auto-refresh the data
                    task_lists = fetch_all_pages(f"{projects_url}/{selected_project_id}/task-lists")
                    tasks = fetch_all_pages(f"{projects_url}/{selected_project_id}/tasks")
                    st.session_state["current_task_lists"] = task_lists or []
                    st.session_state["current_tasks"] = tasks or []
                    st.rerun()
