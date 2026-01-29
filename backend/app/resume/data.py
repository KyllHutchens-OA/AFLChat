"""
Resume Data - Structured JSON storage for RAG retrieval

Kyll Hutchens - Data Analyst / AI Developer
"""

RESUME_DATA = {
    "name": "Kyll Hutchens",
    "title": "Data Analyst & AI Developer",
    "location": "Adelaide, Australia",
    "email": "kyll.hutchens@gmail.com",
    "phone": "For phone number, see original CV",
    "github": "https://github.com/Omnii-Analytics",
    "website": "https://www.kh-applications.com/",

    "summary": """
    Data Analyst transitioning to an AI Developer role with extensive experience in Python, SQL,
    and machine learning. Passionate about leveraging LLMs and AI tools to create cutting-edge
    data solutions and automation products. Fast learner eager to further develop technical
    expertise and contribute innovative solutions in dynamic, forward-thinking environments.
    """,

    "experience": [
        {
            "company": "SA Water",
            "title": "Data + Performance Analyst",
            "start_date": "2023-11",
            "end_date": "Present",
            "location": "Adelaide, Australia",
            "domain": "Government",
            "highlights": [
                "Developed and integrated data automation pipelines to optimise operations staff workflows using Python, allowing staff to identify treatment hazards early and saving hours each day",
                "Built on and managed the 50+ datasets used in the operations performance framework, integrating data from all around the business in various formats (SQL tables, CSV, forms etc.)",
                "Assisting the business in its current transition to Azure data platforms",
                "Managed and ran the wastewater treatment regulatory and internal reporting",
                "Automated all wastewater regulatory reporting, reducing the process from 2-3 weeks annually down to a few hours"
            ],
            "skills_used": ["Python", "Azure", "Data Automation", "Reporting"]
        },
        {
            "company": "Department of Energy, Environment and Climate Action",
            "title": "Data Analyst",
            "start_date": "2019-04",
            "end_date": "2023-11",
            "location": "Victoria, Australia",
            "domain": "Government",
            "highlights": [
                "Liaised with key customers and stakeholders to produce data products to fit their needs",
                "Designed, iterated on, and produced dashboards in Tableau + Power BI for reporting and analysis purposes, enabling customers to delve deeper into their datasets",
                "Extracted, organised, cleaned and automated data and reporting using Python and R",
                "Continually researched best methodology surrounding modelling and reporting of OHS measures",
                "Consulted with business analysis in the design and integration of new Safety database"
            ],
            "skills_used": ["Python", "R", "Tableau", "Power BI", "SQL", "Data Analysis"]
        },
        {
            "company": "Department of Premier and Cabinet, NSW Government",
            "title": "Graduate Analyst",
            "start_date": "2018-02",
            "end_date": "2019-04",
            "location": "Sydney, Australia",
            "domain": "Government",
            "highlights": [
                "Worked on and produced dashboards using Tableau and R Shiny to be fit for purpose within both internal teams and other departments within government",
                "Fulfilling ad-hoc data requests from varying government departments",
                "Automating data collection and manipulation with Python"
            ],
            "skills_used": ["Python", "R", "R Shiny", "Tableau", "Data Analysis"]
        }
    ],

    "skills": {
        "Programming Languages": ["Python", "SQL", "TypeScript", "R"],
        "AI & Machine Learning": ["LangGraph", "OpenAI API", "RAG Architecture", "LLM Agent Development", "Data Science / ML"],
        "Data Tools": ["PostgreSQL", "SQLAlchemy", "Tableau", "Power BI", "Plotly"],
        "Web Development": ["Flask", "React", "WebSocket/Socket.IO", "REST APIs"],
        "DevOps & Cloud": ["Git", "Azure", "Heroku"]
    },

    "education": [
        {
            "institution": "James Cook University",
            "degree": "Master of Data Science",
            "start_year": "2018",
            "end_year": "2020",
            "highlights": []
        }
    ],

    "projects": [
        {
            "name": "AI AFL Analytics Agent",
            "description": "Full-stack AI application enabling natural language queries over AFL statistics (1990-2025) with intelligent visualizations and real-time updates. Live on this website - go back to the landing page and select 'AFL Agent' to try it.",
            "year": "2023-25",
            "technologies": [
                "Python Flask",
                "LangGraph (AI Agent Orchestration)",
                "OpenAI API",
                "React with TypeScript",
                "PostgreSQL with SQLAlchemy",
                "WebSocket (Socket.IO)",
                "Plotly.js (Data Visualization)",
                "Tailwind CSS"
            ],
            "highlights": [
                "Built 6-node LangGraph state machine workflow for multi-step query processing",
                "Implemented NL-to-SQL translation with entity resolution and validation",
                "Created LLM-powered intelligent chart selection system",
                "Real-time WebSocket updates showing agent 'thinking' progress",
                "Conversation memory with follow-up question handling",
                "Statistical analysis pipeline with trend detection and comparison metrics"
            ],
            "link": "https://www.kh-applications.com/"
        },
        {
            "name": "AI Resume Chatbot",
            "description": "RAG-based chatbot enabling natural language interaction with professional resume, featuring career timeline visualization. You're using it right now!",
            "year": "2023-25",
            "technologies": ["Python Flask", "LangGraph", "OpenAI API", "React", "TypeScript", "Plotly.js"],
            "highlights": [
                "2-node LangGraph workflow (Retrieve -> Respond)",
                "Interactive career timeline visualization",
                "WebSocket real-time communication"
            ],
            "link": None
        }
    ],

    "certifications": [],

    "interests": [
        "AI/ML Development",
        "Data Automation",
        "Sports Analytics",
        "Natural Language Processing",
        "Full-Stack Development"
    ]
}


def get_resume_context(query_intent: str = None) -> str:
    """
    Format resume data as context for LLM response generation.

    Args:
        query_intent: Optional intent to focus on specific sections

    Returns:
        Formatted string of resume content
    """
    sections = []

    # Always include basic info
    sections.append(f"Name: {RESUME_DATA['name']}")
    sections.append(f"Title: {RESUME_DATA['title']}")
    sections.append(f"Location: {RESUME_DATA['location']}")
    sections.append(f"Email: {RESUME_DATA['email']}")
    sections.append(f"Phone: {RESUME_DATA['phone']}")
    sections.append(f"GitHub: {RESUME_DATA['github']}")
    sections.append(f"Website: {RESUME_DATA['website']}")
    sections.append(f"Summary: {RESUME_DATA['summary'].strip()}")

    # Experience
    sections.append("\n## Professional Experience")
    for exp in RESUME_DATA['experience']:
        exp_text = f"""
### {exp['title']} at {exp['company']}
- Period: {exp['start_date']} to {exp['end_date']}
- Location: {exp['location']}
- Domain: {exp['domain']}
- Key Achievements:
  - {chr(10) + '  - '.join(exp['highlights'])}
- Technologies: {', '.join(exp['skills_used'])}
"""
        sections.append(exp_text)

    # Skills
    sections.append("\n## Skills")
    for category, skills in RESUME_DATA['skills'].items():
        sections.append(f"**{category}**: {', '.join(skills)}")

    # Projects
    sections.append("\n## Projects")
    for proj in RESUME_DATA['projects']:
        sections.append(f"""
### {proj['name']} ({proj['year']})
{proj['description']}
Technologies: {', '.join(proj['technologies'])}
Highlights: {', '.join(proj['highlights'][:2])}
""")

    return '\n'.join(sections)


def get_skills_for_visualization() -> list:
    """Get flattened skills list."""
    all_skills = []
    for category, skills in RESUME_DATA['skills'].items():
        all_skills.extend(skills)
    return all_skills[:8]  # Top 8 skills


def get_experience_for_visualization() -> list:
    """Get experience formatted for timeline chart."""
    return [
        {
            "company": exp["company"],
            "title": exp["title"],
            "start_date": exp["start_date"],
            "end_date": exp["end_date"],
            "domain": exp["domain"]
        }
        for exp in RESUME_DATA['experience']
    ]
