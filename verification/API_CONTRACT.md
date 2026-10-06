# API Contract Specification

This document details the exact JSON contract, shapes, data types, and UI mapping for the analyzer endpoints and RAG responses in Résumé IQ.

---

## 1. Resume Audit / Review Contract (`POST /api/analyze/resume`)

### Endpoint Details
- **Method**: `POST`
- **Path**: `/api/analyze/resume`
- **Request Body**: Empty (uses active document in the session, `full_doc_text`)
- **Backend Function**: `resume_analyzer.review_resume(resume_text: str) -> dict`

### Success Response Shape (`200 OK`)
```json
{
  "overall_score": 85,
  "axis_scores": {
    "formatting": 80,
    "ats_friendliness": 85,
    "action_verbs": 90,
    "quantified_achievements": 80,
    "section_completeness": 90
  },
  "mistakes_and_missing": [
    "Mistake item 1: Contact information is not formatted consistently...",
    "Mistake item 2: The resume lacks a clear and concise career objective...",
    "Mistake item 3: The 'CORE SKILLS' section could be more specific..."
  ],
  "bullet_rewrites": [
    {
      "weak_original": "Led cross-functional engineering teams to reduce latency by 45%...",
      "strong_version": "Reduced latency by 45% through optimized vector search engine scaling..."
    }
  ]
}
```

### Types & Constraints
- `overall_score`: `int` between 0 and 100.
- `axis_scores`: `object` mapping string keys to `int` (0-100).
  - Standard axes: `formatting`, `ats_friendliness`, `action_verbs`, `quantified_achievements`, `section_completeness`.
- `mistakes_and_missing`: `list[str]` (bullet points of issues detected).
- `bullet_rewrites`: `list[object]` containing:
  - `weak_original`: `str`
  - `strong_version`: `str`

### Error Shape
- Missing active document (`400 Bad Request`):
```json
{
  "detail": "Please upload a resume first to access the intelligence audit."
}
```
- Short / unparseable resume (`422 Unprocessable Entity` or `500`):
```json
{
  "detail": "Resume text is empty or too short for review."
}
```

---

## 2. Interview Questions Contract (`POST /api/analyze/interview_questions`)

### Endpoint Details
- **Method**: `POST`
- **Path**: `/api/analyze/interview_questions` (or tab within Analyze view)
- **Request Body**: Empty (uses session `full_doc_text`)
- **Backend Function**: `resume_analyzer.generate_interview_questions(resume_text: str) -> dict`

### Success Response Shape (`200 OK`)
```json
{
  "questions": [
    {
      "category": "Technical",
      "question": "What is the primary data structure used in Python for data manipulation and analysis?",
      "what_is_tested": "Understanding of Python data structures and their applications.",
      "ideal_answer_outline": "Pandas DataFrames, NumPy arrays, and other relevant data structures."
    },
    {
      "category": "Project/Experience-based",
      "question": "Can you walk me through the process of automating KPI reporting at TE Connectivity?",
      "what_is_tested": "Understanding of project experience and automation techniques.",
      "ideal_answer_outline": "Tools used, data sources, and reporting frequency."
    },
    {
      "category": "Behavioral",
      "question": "Can you describe a situation where you had to communicate complex analytical insights to a non-technical stakeholder?",
      "what_is_tested": "Understanding of communication skills and stakeholder management.",
      "ideal_answer_outline": "Storytelling techniques, data visualization, and presentation skills."
    }
  ]
}
```

### Types & Constraints
- `questions`: `list[object]` (up to 10 questions).
- Each item:
  - `category`: `str`, one of `"Technical"`, `"Project/Experience-based"`, `"Behavioral"` (or any domain-specific category).
  - `question`: `str` (the interview prompt).
  - `what_is_tested`: `str` (evaluator rubric).
  - `ideal_answer_outline`: `str` (key response points).

---

## 3. Job Description Matcher Contract (`POST /api/analyze/jd`)

### Endpoint Details
- **Method**: `POST`
- **Path**: `/api/analyze/jd`
- **Request Modes**:
  - Multipart Form with `jd_file: UploadFile` OR `jd_text: str`
- **Backend Function**: `resume_analyzer.match_job_description(resume_text: str, jd_text: str) -> dict`

### Success Response Shape (`200 OK`)
```json
{
  "match_percentage": 92,
  "matched_keywords": [
    "Python",
    "AI/ML",
    "RAG architectures",
    "LangChain",
    "Vector databases",
    "ChromaDB",
    "FastAPI",
    "Docker",
    "AWS",
    "Kubernetes"
  ],
  "missing_keywords": [
    "Go",
    "SQL",
    "Streamlit",
    "React",
    "PostgreSQL"
  ],
  "edit_suggestions": [
    "Consider adding experience with GraphQL APIs to match the JD requirement.",
    "Highlight experience with Vector Search and Semantic Routing to match the JD requirement.",
    "Emphasize the ability to design and implement production-ready RAG architectures to match the JD requirement."
  ]
}
```

### Types & Constraints
- `match_percentage`: `int` (0 to 100).
- `matched_keywords`: `list[str]` (keywords present in both resume and JD).
- `missing_keywords`: `list[str]` (keywords in JD missing from resume).
- `edit_suggestions`: `list[str]` (targeted actionable recommendations).

---

## 4. UI Score Color Cutoffs & Gauge Semantics

From `app.py` inspection:
- Score $\ge 80$: **High / Green** (`#10B981` / Emerald)
- Score $60 - 79$: **Moderate / Amber** (`#F59E0B` / Amber)
- Score $< 60$: **Needs Improvement / Rose** (`#EF4444` / Red)
- Gauge visual: Circular SVG meter with stroke dashoffset calculation:
  $$\text{dashoffset} = \text{circumference} \times (1 - \frac{\text{score}}{100})$$
  $$\text{circumference} = 2 \times \pi \times \text{radius}$$
