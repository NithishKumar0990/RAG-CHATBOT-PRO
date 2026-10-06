# resume_analyzer.py
import json
import re
import sys
import streamlit as st
from rag_pipeline import _get_llm, llm

# Dedicated LLM instance for analysis tasks with larger output token limit (1024)
analyzer_llm = _get_llm(max_new_tokens=1024, temperature=0.01) if hasattr(_get_llm, '__call__') else llm

def _clean_and_parse_json(raw_text: str) -> dict:
    """
    Safely extract and parse JSON from raw LLM output text.
    Strips markdown code blocks, trailing commas, and extracts JSON objects.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("LLM returned an empty response.")
        
    text = raw_text.strip()
    
    # Strip markdown code blocks like ```json ... ```
    if "```" in text:
        # Match content inside ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
            
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
        
    # Attempt to locate first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    raise ValueError(f"Failed to parse valid JSON from LLM output: {raw_text[:200]}...")


@st.cache_data(ttl=3600)
def generate_interview_questions(resume_text: str) -> dict:
    """
    Feature A: Generate 10 interview questions across 3 categories:
    - Technical (from listed skills)
    - Project/Experience-based (from actual work history)
    - Behavioral

    Returns a dict with key 'questions' containing 10 question objects.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError("Resume text is empty or too short for analysis.")

    prompt_text = f"""Analyze the resume below and generate exactly 10 high-quality interview questions categorized into: Technical, Project/Experience-based, and Behavioral.

CRITICAL FORMATTING INSTRUCTIONS:
- You MUST return ONLY a valid JSON object starting with '{{"' and ending with '}}'.
- Do NOT output any intro/outro text, markdown fences, or conversational preamble.
- Keep 'what_is_tested' under 15 words and 'ideal_answer_outline' under 25 words per question so the JSON is concise and complete.

Structure:
{{
  "questions": [
    {{
      "category": "Technical",
      "question": "Question text...",
      "what_is_tested": "Brief explanation...",
      "ideal_answer_outline": "Key points..."
    }}
  ]
}}

Resume Content:
{resume_text}
"""

    # Call LLM helper
    try:
        # We can construct input dict for LLM chain
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        
        chain = PromptTemplate.from_template("{prompt}") | analyzer_llm | StrOutputParser()
        raw_output = chain.invoke({"prompt": prompt_text})
        data = _clean_and_parse_json(str(raw_output))
        
        if "questions" not in data or not isinstance(data["questions"], list):
            raise ValueError("Response missing 'questions' array.")
            
        data["questions"] = data["questions"][:10]
        return data
    except Exception as e:
        print(f"[ANALYZER ERROR] generate_interview_questions failed: {e}", file=sys.stderr)
        raise e


@st.cache_data(ttl=3600)
def review_resume(resume_text: str) -> dict:
    """
    Feature B: Review resume, score out of 100 across 5 axes, list mistakes/missing sections,
    and provide 3 'before & after' bullet point rewrites.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError("Resume text is empty or too short for review.")

    prompt_text = f"""Evaluate the resume below across 5 core evaluation axes: formatting, ats_friendliness, action_verbs, quantified_achievements, section_completeness.

CRITICAL FORMATTING INSTRUCTIONS:
- You MUST return ONLY a valid JSON object starting with '{{"' and ending with '}}'.
- Do NOT output any intro/outro text, markdown fences, or conversational preamble.
- Keep list items concise so output is complete.

Structure:
{{
  "overall_score": 85,
  "axis_scores": {{
    "formatting": 80,
    "ats_friendliness": 85,
    "action_verbs": 90,
    "quantified_achievements": 80,
    "section_completeness": 90
  }},
  "mistakes_and_missing": [
    "Mistake item 1...",
    "Mistake item 2..."
  ],
  "bullet_rewrites": [
    {{
      "weak_original": "Weak original bullet from resume",
      "strong_version": "Improved action-driven bullet point with metrics"
    }},
    {{
      "weak_original": "...",
      "strong_version": "..."
    }},
    {{
      "weak_original": "...",
      "strong_version": "..."
    }}
  ]
}}

Resume Content:
{resume_text}
"""

    try:
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        
        chain = PromptTemplate.from_template("{prompt}") | analyzer_llm | StrOutputParser()
        raw_output = chain.invoke({"prompt": prompt_text})
        data = _clean_and_parse_json(str(raw_output))
        
        required_keys = ["overall_score", "axis_scores", "mistakes_and_missing", "bullet_rewrites"]
        for k in required_keys:
            if k not in data:
                raise ValueError(f"Response missing required JSON key: {k}")
                
        return data
    except Exception as e:
        print(f"[ANALYZER ERROR] review_resume failed: {e}", file=sys.stderr)
        raise e


@st.cache_data(ttl=3600)
def match_job_description(resume_text: str, jd_text: str) -> dict:
    """
    Feature C: Compare resume against Job Description (JD).
    Outputs match percentage, matched keywords, missing keywords, and 3 specific resume edit suggestions.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        raise ValueError("Resume text is empty or too short for JD matching.")
    if not jd_text or len(jd_text.strip()) < 30:
        raise ValueError("Job description is empty or too short.")

    prompt_text = f"""Compare the candidate's resume against the Job Description (JD) below.

CRITICAL FORMATTING INSTRUCTIONS:
- You MUST return ONLY a valid JSON object starting with '{{"' and ending with '}}'.
- Do NOT output any intro/outro text, markdown fences, or conversational preamble.

Structure:
{{
  "match_percentage": 78,
  "matched_keywords": ["Keyword 1", "Keyword 2", ...],
  "missing_keywords": ["Missing Keyword 1", "Missing Keyword 2", ...],
  "edit_suggestions": [
    "Actionable recommendation 1 targeting this exact JD...",
    "Actionable recommendation 2...",
    "Actionable recommendation 3..."
  ]
}}

Candidate Resume:
{resume_text}

Job Description:
{jd_text}
"""

    try:
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        
        chain = PromptTemplate.from_template("{prompt}") | analyzer_llm | StrOutputParser()
        raw_output = chain.invoke({"prompt": prompt_text})
        data = _clean_and_parse_json(str(raw_output))
        
        required_keys = ["match_percentage", "matched_keywords", "missing_keywords", "edit_suggestions"]
        for k in required_keys:
            if k not in data:
                raise ValueError(f"Response missing required JSON key: {k}")
                
        return data
    except Exception as e:
        print(f"[ANALYZER ERROR] match_job_description failed: {e}", file=sys.stderr)
        raise e
