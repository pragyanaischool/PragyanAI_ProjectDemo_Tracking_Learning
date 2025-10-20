import streamlit as st
import pandas as pd
from utils import connect_to_google_sheets, load_all_projects, logger

try:
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import WebBaseLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser
except ImportError:
    st.error("LLM dependencies are not installed. Please run: pip install -r requirements.txt")

def show_peer_learning_page():
    st.title("🧑‍🎓 PragyanAI - Peer Learning Hub")
    st.write("Explore projects from past and present events.")
    
    client = connect_to_google_sheets()
    if not client: return
    
    projects_df = load_all_projects(client)
    if projects_df.empty:
        st.warning("No projects found across any approved events.")
        return

    if 'ProjectTitle' not in projects_df.columns:
        st.error("Could not find 'ProjectTitle' column in project data.")
        return

    project_choice = st.selectbox("Select a project to view", options=projects_df['ProjectTitle'].unique())
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if project_choice:
        project_details = projects_df[projects_df['ProjectTitle'] == project_choice].iloc[0]
        
        st.header(project_details.get('ProjectTitle', 'N/A'))
        st.caption(f"By {project_details.get('StudentFullName', 'N/A')} | Event: {project_details.get('EventName', 'N/A')}")
        st.write(f"**Description:** {project_details.get('Description', 'N/A')}")
        
        c1, c2, c3, c4 = st.columns(4)
        if project_details.get('ReportLink'): c1.link_button("📄 View Report", project_details['ReportLink'])
        if project_details.get('PresentationLink'): c2.link_button("🖥️ View Presentation", project_details['PresentationLink'])
        if project_details.get('GitHubLink'): c3.link_button("💻 View Code", project_details['GitHubLink'])
        if project_details.get('Linkedin_Project_Post_Link'): c4.link_button("🔗 LinkedIn", project_details['Linkedin_Project_Post_Link'])

        if project_details.get('YouTubeLink'): 
            st.video(project_details['YouTubeLink'])
        
        # RAG Q&A Section
        st.markdown("---")
        st.subheader("🤖 Ask a question about this project's report")
        api_key = st.session_state.get("groq_api_key")
        report_url = project_details.get('ReportLink')
        
        if not api_key:
            st.warning("Please enter your GROQ API key in the sidebar to use this feature.")
            return

        if not report_url:
            st.info("This project does not have a report link for the Q&A bot.")
            return
            
        question = st.text_input("Your question:")
        if question:
            with st.spinner("Analyzing document and generating answer..."):
                try:
                    loader = WebBaseLoader(report_url)
                    docs = loader.load()
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                    splits = text_splitter.split_documents(docs)
                    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                    vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)
                    llm = ChatGroq(temperature=0, groq_api_key=api_key, model_name="llama3-70b-8192")
                    
                    retriever = vectorstore.as_retriever()
                    template = "Answer the question based only on the context:\n\n{context}\n\nQuestion: {question}"
                    prompt = ChatPromptTemplate.from_template(template)

                    rag_chain = ({"context": retriever, "question": RunnablePassthrough()} | prompt | llm | StrOutputParser())
                    response = rag_chain.invoke(question)
                    st.success("Answer:")
                    st.write(response)
                except Exception as e:
                    st.error(f"Failed to process the document. Error: {e}")
                    logger.error(f"RAG process failed for URL {report_url}: {e}")
    st.markdown('</div>', unsafe_allow_html=True)
