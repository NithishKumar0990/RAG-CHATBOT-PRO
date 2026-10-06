# verify_platform.py
import io
import sys
from resume_analyzer import generate_interview_questions, review_resume, match_job_description
from rag_pipeline import answer_question, index_uploaded_document, clear_uploaded_documents, FALLBACK_MSG
from document_parser import parse_document

# Force utf-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class MockFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
    def getvalue(self) -> bytes:
        return self._data

sample_resume = """
Tushant Chaudhari
Phone: +91-7522971555 | Email: tushantac2003@gmail.com

ABOUT
Entry-level Data Analyst with training in data analytics and machine learning.
Proficient in Python, SQL, Excel, and Power BI for data analysis and visualization.
Experienced in data cleaning, EDA, and predictive modelling.

WORK EXPERIENCE
TE Connectivity Ind Pvt Ltd (July 2024 - Sep 2024)
Intern - Product Management (E-Mobility)
• Managed and analyzed project pipeline data using MS Excel for revenue forecasting.
• Prepared technical and business review presentations using MS PowerPoint for management meetings.

SKILLS
Programming: Python (Pandas, NumPy, Scikit-Learn), SQL (MySQL, PostgreSQL)
Tools & Visualization: Power BI, MS Excel, Jupyter Notebook, Git, GitHub
Data Analysis: Data Cleaning, EDA, Predictive Modeling, Regression

PROJECTS
Bank Loan Prediction | Machine Learning
• Developed a Decision Tree model to predict loan approval and support credit risk assessment.
• Performed data preprocessing, feature engineering, and model evaluation in Python.
"""

sample_jd = """
Job Title: Data Analyst
Company: FinTech Solutions Inc.

Requirements:
- Bachelor's degree in Computer Science, Data Science, or related field.
- 1+ years experience in Data Analysis or Data Engineering.
- Strong proficiency in SQL (writing complex queries, joins, aggregations) and Python (Pandas).
- Hands-on experience building interactive dashboards in Power BI or Tableau.
- Knowledge of ETL pipelines, data warehousing (Snowflake), and predictive modeling.
- Excellent communication and presentation skills to present insights to leadership.
"""

def verify_all():
    print("==================================================")
    print("RUNNING PLATFORM VERIFICATION TESTS A1 - A4")
    print("==================================================")
    results = {}

    # ------------------------------------------------------------------
    # Test A1: Interview Question Generator
    # ------------------------------------------------------------------
    print("\n--- Test A1: Interview Question Generator ---")
    try:
        q_data = generate_interview_questions(sample_resume)
        questions = q_data.get("questions", [])
        print(f"Total questions generated: {len(questions)}")
        cats = set(q.get("category") for q in questions)
        print(f"Categories detected: {cats}")
        
        has_10_q = len(questions) == 10
        has_fields = all("question" in q and "what_is_tested" in q and "ideal_answer_outline" in q for q in questions)
        
        if has_10_q and has_fields:
            print("[PASS] A1: Generated 10 categorized questions with tested competencies and ideal outlines.")
            results["A1"] = "PASS"
        else:
            print(f"[FAIL] A1: Question count: {len(questions)}, Valid fields: {has_fields}")
            results["A1"] = "FAIL"
    except Exception as e:
        print(f"[FAIL] A1: Exception during questions generation: {e}")
        results["A1"] = "FAIL"

    # ------------------------------------------------------------------
    # Test A2: Resume Review & Score
    # ------------------------------------------------------------------
    print("\n--- Test A2: Resume Review & Score ---")
    try:
        rev = review_resume(sample_resume)
        score = rev.get("overall_score")
        axes = rev.get("axis_scores", {})
        mistakes = rev.get("mistakes_and_missing", [])
        rewrites = rev.get("bullet_rewrites", [])
        
        print(f"Overall score: {score}/100")
        print(f"Axes evaluated: {list(axes.keys())}")
        print(f"Mistakes count: {len(mistakes)}, Bullet rewrites count: {len(rewrites)}")
        
        valid_score = isinstance(score, (int, float)) and 0 <= score <= 100
        valid_axes = len(axes) == 5
        valid_rewrites = len(rewrites) == 3 and all("weak_original" in r and "strong_version" in r for r in rewrites)
        
        if valid_score and valid_axes and valid_rewrites:
            print("[PASS] A2: Resume review rendered /100 score, 5 axes, mistakes, and 3 before/after bullets cleanly.")
            results["A2"] = "PASS"
        else:
            print(f"[FAIL] A2: Score valid: {valid_score}, Axes valid: {valid_axes}, Rewrites valid: {valid_rewrites}")
            results["A2"] = "FAIL"
    except Exception as e:
        print(f"[FAIL] A2: Exception during resume review: {e}")
        results["A2"] = "FAIL"

    # ------------------------------------------------------------------
    # Test A3: Job Description Matcher
    # ------------------------------------------------------------------
    print("\n--- Test A3: Job Description Matcher ---")
    try:
        match_res = match_job_description(sample_resume, sample_jd)
        match_pct = match_res.get("match_percentage")
        matched_kw = match_res.get("matched_keywords", [])
        missing_kw = match_res.get("missing_keywords", [])
        edits = match_res.get("edit_suggestions", [])
        
        print(f"Match percentage: {match_pct}%")
        print(f"Matched keywords: {matched_kw}")
        print(f"Missing keywords: {missing_kw}")
        print(f"Edit suggestions count: {len(edits)}")
        
        valid_match = isinstance(match_pct, (int, float)) and 0 <= match_pct <= 100
        has_keywords = len(matched_kw) > 0 and len(missing_kw) > 0
        has_edits = len(edits) >= 3
        
        if valid_match and has_keywords and has_edits:
            print("[PASS] A3: JD matcher successfully returned match %, keywords, and edit suggestions.")
            results["A3"] = "PASS"
        else:
            print(f"[FAIL] A3: Match valid: {valid_match}, Keywords present: {has_keywords}, Edits count: {len(edits)}")
            results["A3"] = "FAIL"
    except Exception as e:
        print(f"[FAIL] A3: Exception during JD match: {e}")
        results["A3"] = "FAIL"

    # ------------------------------------------------------------------
    # Test A4 (Regression): Chat Mode functionality
    # ------------------------------------------------------------------
    print("\n--- Test A4 (Regression): Chat Mode Functionality ---")
    try:
        # Index sample resume
        index_uploaded_document(sample_resume, filename="tushant_resume.txt")
        
        # Test 1: "What are my skills?"
        res_skills = answer_question("What are my skills?")
        ans_skills = res_skills.get("answer", "")
        sources_skills = res_skills.get("sources", [])
        print(f"Skills answer snippet: {ans_skills[:100]}...")
        print(f"Skills sources count: {len(sources_skills)}")
        
        skills_pass = len(sources_skills) > 0 and ("python" in ans_skills.lower() or "sql" in ans_skills.lower() or "power bi" in ans_skills.lower())
        
        # Test 2: "hi" fallback
        res_hi = answer_question("hi")
        ans_hi = res_hi.get("answer", "")
        sources_hi = res_hi.get("sources", [])
        print(f"Hi answer: {ans_hi} | sources: {len(sources_hi)}")
        
        hi_pass = ans_hi == FALLBACK_MSG and len(sources_hi) == 0
        
        if skills_pass and hi_pass:
            print("[PASS] A4: Chat mode RAG retrieval ('What are my skills?') and threshold fallback ('hi') are fully functional.")
            results["A4"] = "PASS"
        else:
            print(f"[FAIL] A4: Skills pass: {skills_pass}, Hi fallback pass: {hi_pass}")
            results["A4"] = "FAIL"
    except Exception as e:
        print(f"[FAIL] A4: Exception during Chat mode test: {e}")
        results["A4"] = "FAIL"

    print("\n==================================================")
    print("FINAL SUMMARY OF PLATFORM TESTS A1 - A4:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("==================================================")
    
    if all(v == "PASS" for v in results.values()):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    verify_all()
