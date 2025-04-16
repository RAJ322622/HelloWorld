# Add this to the menu list (around line 87)
menu = ["Register", "Login", "Take Quiz", "Change Password", "Professor Panel", "Professor Monitoring Panel", "Dean Academics and HOD", "View Recorded Video"]

# Add this new section after the "Professor Monitoring Panel" section (around line 1027)
elif choice == "Dean Academics and HOD":
    st.subheader("\U0001F468‍\U0001F393 Dean Academics & HOD Dashboard")
    
    # Authentication for Dean/HOD
    if 'dean_verified' not in st.session_state:
        secret_key = st.text_input("Enter Dean/HOD Secret Key to continue", type="password")
        
        if st.button("Verify Key"):
            if secret_key == "DEAN@123":  # You can change this secret key
                st.session_state.dean_verified = True
                st.rerun()
            else:
                st.error("Invalid secret key! Access denied.")
    else:
        st_autorefresh(interval=10000, key="dean_refresh")
        
        # Section selection
        sections = ["A", "B", "C"]  # Add more sections if needed
        selected_section = st.selectbox("Select Section", sections)
        
        # Section-wise dashboard
        st.markdown(f"### {selected_section} Section Monitoring")
        
        # 1. Active Students
        st.markdown("#### Currently Active Students")
        live_students = get_live_students()
        section_students = [s for s in live_students if s.endswith(selected_section)]
        
        if not section_students:
            st.write("No active students in this section.")
        else:
            st.write(f"Active students ({len(section_students)}):")
            for student in section_students:
                st.write(f"- {student}")
        
        # 2. Section Results
        st.markdown("---")
        st.markdown(f"#### {selected_section} Section Results")
        section_file = f"{selected_section}_results.csv"
        
        if os.path.exists(section_file):
            df = pd.read_csv(section_file)
            
            # Statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Students", len(df))
            with col2:
                avg_score = df['Score'].mean()
                st.metric("Average Score", f"{avg_score:.1f}/{len(QUESTIONS)}")
            with col3:
                pass_rate = (len(df[df['Score'] >= len(QUESTIONS)/2]) / len(df)) * 100
                st.metric("Pass Rate", f"{pass_rate:.1f}%")
            
            # Detailed results
            st.dataframe(df.sort_values("Score", ascending=False))
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label=f"Download {selected_section} Results",
                data=csv,
                file_name=f"{selected_section}_quiz_results.csv",
                mime="text/csv"
            )
        else:
            st.warning(f"No results available for {selected_section} section yet.")
        
        # 3. All Sections Summary
        st.markdown("---")
        st.markdown("### All Sections Summary")
        
        all_sections_data = []
        for sec in sections:
            sec_file = f"{sec}_results.csv"
            if os.path.exists(sec_file):
                sec_df = pd.read_csv(sec_file)
                sec_count = len(sec_df)
                sec_avg = sec_df['Score'].mean()
                sec_pass = (len(sec_df[sec_df['Score'] >= len(QUESTIONS)/2]) / sec_count) * 100
                all_sections_data.append({
                    "Section": sec,
                    "Students": sec_count,
                    "Avg Score": f"{sec_avg:.1f}/{len(QUESTIONS)}",
                    "Pass Rate": f"{sec_pass:.1f}%"
                })
        
        if all_sections_data:
            summary_df = pd.DataFrame(all_sections_data)
            st.table(summary_df)
            
            # Visualization
            st.markdown("#### Performance Comparison")
            fig = px.bar(summary_df, 
                        x="Section", 
                        y="Pass Rate",
                        title="Pass Rate by Section",
                        labels={"Pass Rate": "Pass Rate (%)"})
            st.plotly_chart(fig)
        else:
            st.warning("No section data available yet.")
        
        # Logout button
        if st.button("Logout"):
            del st.session_state.dean_verified
            st.rerun()
