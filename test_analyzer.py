# test_analyzer.py
import io
import sys
from resume_analyzer import generate_interview_questions, review_resume, match_job_description

# Force utf-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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

def run_tests():
    print("=== TESTING RESUME ANALYZER ENGINE ===")
    
    # Feature A
    print("\n--- Testing Feature A: Interview Questions ---")
    q_data = generate_interview_questions(sample_resume)
    questions = q_data.get("questions", [])
    print(f"Total questions generated: {len(questions)}")
    cats = {}
    for q in questions:
        c = q.get("category", "Unknown")
        cats[c] = cats.get(c, 0) + 1
        print(f"[{c}] Q: {q.get('question')[:80]}...")
        print(f"    Tested: {q.get('what_is_tested')[:60]}...")
        print(f"    Outline: {q.get('ideal_answer_outline')[:60]}...")
    print(f"Categories breakdown: {cats}")
    
    assert len(questions) == 10, f"Expected 10 questions, got {len(questions)}"

    # Feature B
    print("\n--- Testing Feature B: Resume Review ---")
    rev = review_resume(sample_resume)
    print(f"Overall Score: {rev.get('overall_score')}/100")
    print(f"Axis Scores: {rev.get('axis_scores')}")
    print(f"Mistakes/Missing count: {len(rev.get('mistakes_and_missing', []))}")
    print(f"Bullet Rewrites count: {len(rev.get('bullet_rewrites', []))}")
    for bw in rev.get('bullet_rewrites', []):
        print(f"  Weak: {bw.get('weak_original')}")
        print(f"  Strong: {bw.get('strong_version')}\n")
    assert "overall_score" in rev
    assert len(rev.get("bullet_rewrites", [])) == 3

    # Feature C
    print("\n--- Testing Feature C: Job Description Matcher ---")
    match = match_job_description(sample_resume, sample_jd)
    print(f"Match Score: {match.get('match_percentage')}%")
    print(f"Matched Keywords: {match.get('matched_keywords')}")
    print(f"Missing Keywords: {match.get('missing_keywords')}")
    print(f"Edit Suggestions count: {len(match.get('edit_suggestions', []))}")
    for idx, s in enumerate(match.get("edit_suggestions", []), 1):
        print(f"  Suggestion {idx}: {s}")
    assert "match_percentage" in match

    print("\n=========================================")
    print("ALL RESUME ANALYZER ENGINE TESTS PASSED!")
    print("=========================================")

if __name__ == "__main__":
    run_tests()
