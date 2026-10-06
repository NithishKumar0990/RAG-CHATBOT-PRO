# resume_analyzer.py
import json
import re
import sys
from rag_pipeline import _get_llm, llm

analyzer_llm = _get_llm(max_new_tokens=1500, temperature=0.05) if hasattr(_get_llm, '__call__') else llm

def _clean_and_parse_json(raw_text: str) -> dict:
    if not raw_text or not raw_text.strip():
        raise ValueError("LLM returned an empty response.")
    text = raw_text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match: text = match.group(1).strip()
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try: return json.loads(text[start:end+1])
        except json.JSONDecodeError: pass
    raise ValueError(f"Failed to parse JSON: {raw_text[:200]}...")

def _invoke_llm(prompt_text: str) -> dict:
    from langchain_core.prompts import PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    chain = PromptTemplate.from_template("{prompt}") | analyzer_llm | StrOutputParser()
    raw_output = chain.invoke({"prompt": prompt_text})
    return _clean_and_parse_json(str(raw_output))

def generate_interview_questions(resume_text: str) -> dict:
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError("Resume text is too short.")
    
    prompt_text = f"""You are an expert technical recruiter. Analyze the resume and generate exactly 10 high-quality interview questions.
Categorize them into: "Technical", "Project/Experience", and "Behavioral".

CRITICAL: Return ONLY valid JSON. No markdown, no intro/outro text.

Structure:
{{
  "questions": [
    {{
      "category": "Technical",
      "question": "Question text...",
      "what_is_tested": "Brief explanation (<= 15 words)",
      "ideal_answer_outline": "Key points to look for (<= 25 words)"
    }}
  ]
}}

Resume:
{resume_text}
"""
    data = _invoke_llm(prompt_text)
    if "questions" not in data: raise ValueError("Missing 'questions' key.")
    data["questions"] = data["questions"][:10]
    return data

def review_resume(resume_text: str) -> dict:
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError("Resume text is too short.")

    prompt_text = f"""You are an expert ATS (Applicant Tracking System) and resume auditor. Evaluate the resume across 5 axes.
Be highly critical. If metrics are missing, score 'quantified_achievements' below 50.

CRITICAL: Return ONLY valid JSON. No markdown, no intro/outro text.

Structure:
{{
  "overall_score": 85,
  "axis_scores": {{
    "formatting": 80,
    "ats_friendliness": 85,
    "action_verbs": 90,
    "quantified_achievements": 40,
    "section_completeness": 90
  }},
  "axis_feedback": {{
    "formatting": "Brief reason for score...",
    "ats_friendliness": "Brief reason for score...",
    "action_verbs": "Brief reason for score...",
    "quantified_achievements": "Brief reason for score...",
    "section_completeness": "Brief reason for score..."
  }},
  "mistakes_and_missing": ["Mistake 1", "Mistake 2"],
  "bullet_rewrites": [
    {{ "weak_original": "Weak bullet", "strong_version": "Strong, metric-driven bullet" }}
  ]
}}

Resume:
{resume_text}
"""
    data = _invoke_llm(prompt_text)
    for k in ["overall_score", "axis_scores", "axis_feedback", "mistakes_and_missing", "bullet_rewrites"]:
        if k not in data: raise ValueError(f"Missing key: {k}")
    return data

def match_job_description(resume_text: str, jd_text: str) -> dict:
    if not resume_text or len(resume_text.strip()) < 50: raise ValueError("Resume too short.")
    if not jd_text or len(jd_text.strip()) < 30: raise ValueError("JD too short.")

    prompt_text = f"""Compare the resume against the Job Description. Categorize keywords into Hard Skills, Soft Skills, and Tools/Technologies.
Identify what is matched and what is missing in each category.

CRITICAL: Return ONLY valid JSON. No markdown, no intro/outro text.

Structure:
{{
  "match_percentage": 78,
  "matched_keywords": {{
    "hard_skills": ["Skill 1"],
    "soft_skills": ["Skill 2"],
    "tools": ["Tool 1"]
  }},
  "missing_keywords": {{
    "hard_skills": ["Missing Skill 1"],
    "soft_skills": ["Missing Skill 2"],
    "tools": ["Missing Tool 1"]
  }},
  "edit_suggestions": ["Actionable suggestion 1", "Suggestion 2", "Suggestion 3"]
}}

Resume: {resume_text}
JD: {jd_text}
"""
    data = _invoke_llm(prompt_text)
    for k in ["match_percentage", "matched_keywords", "missing_keywords", "edit_suggestions"]:
        if k not in data: raise ValueError(f"Missing key: {k}")
    return data

def generate_resume_summary(resume_text: str, jd_text: str) -> dict:
    """NEW FEATURE: Generates a tailored professional summary."""
    if not resume_text or len(resume_text.strip()) < 50: raise ValueError("Resume too short.")
    
    jd_context = jd_text if jd_text and len(jd_text.strip()) > 20 else "General industry standards."
    
    prompt_text = f"""Write a powerful, 3-sentence professional summary for the top of a resume. 
Tailor it to highlight the candidate's core strengths and align them with the target role.
Do not use first-person pronouns (I, me, my). Start directly with an action adjective or title.

CRITICAL: Return ONLY valid JSON. No markdown, no intro/outro text.

Structure:
{{
  "summary": "The 3-sentence professional summary text.",
  "why_this_works": "Brief explanation of why this summary is effective for this specific role."
}}

Resume: {resume_text}
Target Role Context: {jd_context}
"""
    data = _invoke_llm(prompt_text)
    if "summary" not in data: raise ValueError("Missing 'summary' key.")
    return data
