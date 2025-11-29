from django.shortcuts import render
import ollama
import random
import json
import PyPDF2
from docx import Document

from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db.models import Avg
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


from .models import UserProfile, Question, InterviewResult
from .serializers import QuestionSerializer, UserProfileSerializer


# ============================================================
# DEFAULT OPTIONS
# ============================================================

DEFAULT_ROLES = [
    "frontend developer",
    "backend developer",
    "full stack developer",
    "devops engineer",
    "software engineer",
    "data analyst",
    "data scientist",
]

DEFAULT_SKILLS = [
    "javascript",
    "react",
    "python",
    "django",
    "java",
    "mysql",
    "html",
    "css",
]


# ============================================================
# UTILS
# ============================================================

def normalize(text):
    return (text or "").strip().lower()


def save_question_if_new(text, role, skill, level):
    text = text.strip()
    role = normalize(role)
    skill = normalize(skill)
    level = normalize(level)

    exists = Question.objects.filter(
        text__iexact=text,
        role=role,
        skill=skill,
        level=level,
    ).exists()

    if not exists:
        Question.objects.create(
            text=text,
            role=role,
            skill=skill,
            level=level
        )


def save_role_if_new(role):
    role = normalize(role)
    if not role:
        return

    exists = Question.objects.filter(role=role).exists()
    if not exists:
        Question.objects.create(
            text=f"[auto-role:{role}]",
            role=role,
            skill="",
            level="meta"
        )


def save_skill_if_new(skill):
    skill = normalize(skill)
    if not skill:
        return

    exists = Question.objects.filter(skill=skill).exists()
    if not exists:
        Question.objects.create(
            text=f"[auto-skill:{skill}]",
            role="",
            skill=skill,
            level="meta"
        )


# ============================================================
# REGISTER
# ============================================================

@api_view(["POST"])
def register_user(request):
    full_name = request.data.get("full_name")
    username = request.data.get("username")
    email = request.data.get("email")
    password = request.data.get("password")
    mobile = request.data.get("mobile")
    role = request.data.get("role")

    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already exists"}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already used"}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)

    UserProfile.objects.create(
        user=user,
        full_name=full_name,
        mobile=mobile,
        role=role
    )

    return Response({"message": "Account created successfully!"})


# ============================================================
# LOGIN
# ============================================================

@api_view(["POST"])
def login_user(request):
    username = request.data.get("username")
    password = request.data.get("password")

    user = authenticate(username=username, password=password)
    if not user:
        return Response({"error": "Invalid credentials"}, status=400)

    refresh = RefreshToken.for_user(user)

    return Response({
        "message": "Login successful",
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "username": user.username,
        "is_admin": user.is_staff
    })



# ============================================================
# PROFILE
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile(request):
    profile = UserProfile.objects.get(user=request.user)
    return Response(UserProfileSerializer(profile).data)


# ============================================================
# DASHBOARD
# ============================================================

@api_view(["GET"])
def dashboard_stats(request):
    user = request.user

    total = InterviewResult.objects.filter(user=user).count()
    avg = InterviewResult.objects.filter(user=user).aggregate(avg=Avg("score"))["avg"] or 0

    return Response({
        "total_attempts": total,
        "average_score": round(avg, 1)
    })


# ============================================================
# DYNAMIC ROLES / SKILLS
# ============================================================

@api_view(["GET"])
def get_roles(request):
    roles = list(Question.objects.values_list("role", flat=True).distinct())
    roles = [r for r in roles if r]
    return Response(sorted(set(roles + DEFAULT_ROLES)))


@api_view(["GET"])
def get_skills(request):
    skills = list(Question.objects.values_list("skill", flat=True).distinct())
    skills = [s for s in skills if s]
    return Response(sorted(set(skills + DEFAULT_SKILLS)))


# ============================================================
# GET QUESTION
# ============================================================

@api_view(["GET"])
def get_question(request):
    role = normalize(request.GET.get("role"))
    skill = normalize(request.GET.get("skill"))
    level = normalize(request.GET.get("level"))

    qs = Question.objects.all()

    if role:
        qs = qs.filter(role=role)
    if skill:
        qs = qs.filter(skill=skill)
    if level:
        qs = qs.filter(level=level)

    if qs.exists():
        return Response(QuestionSerializer(random.choice(list(qs))).data)

    # AI fallback
    prompt = f"""
    Generate ONE interview question.
    Role: {role or 'general'}
    Skill: {skill or 'general'}
    Difficulty: {level or 'easy'}
    Return ONLY the question.
    """

    ai = ollama.chat(
        model="llama3.1:8b",
        messages=[{"role": "user", "content": prompt}]
    )

    q_text = ai["message"]["content"].strip()

    save_question_if_new(q_text, role or "general", skill or "general", level or "easy")

    return Response({"text": q_text})


# ============================================================
# EVALUATE ANSWER + SAVE SESSION
# ============================================================

@api_view(["POST"])
def evaluate_answer(request):
    question = request.data.get("question")
    answer = request.data.get("answer")
    session_id = request.data.get("session_id")
    user = request.user if request.user.is_authenticated else None

    if not session_id:
        return Response({"error": "session_id required"}, status=400)

    # ============================================================
    # AI Prompt — Always produce FULL correct answer
    # ============================================================
    prompt = f"""
You are an interview evaluator. Follow these rules STRICTLY and output ONLY VALID JSON.

1. If the given answer is meaningless, random, incorrect, or unrelated:
   - score = 0
   - strengths = "None"
   - weaknesses = "Answer is meaningless, random, or incorrect"
   - improved_answer = "Write the full correct and ideal answer to the question."

2. If the answer is partially correct:
   - Give a fair score between 1 and 7
   - Identify strengths and weaknesses
   - improved_answer must contain the correct, complete explanation.

3. If the answer is fully correct:
   - Give a score between 8 and 10
   - improved_answer must still give an improved, professional version.

Your improved_answer MUST ALWAYS contain the full correct explanation the candidate should have given.

Evaluate:

Question: {question}
Answer: {answer}

Return JSON ONLY:
{{
  "score": number,
  "strengths": "string",
  "weaknesses": "string",
  "improved_answer": "string"
}}
"""

    # Call Llama model
    try:
        ai = ollama.chat(
            model="llama3.1:8b",
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        return Response({"error": "AI model error", "details": str(e)}, status=500)

    # ============================================================
    # Sanitize JSON
    # ============================================================
    raw = ai["message"]["content"].strip()
    raw = raw.replace("```json", "").replace("```", "")

    # Extract JSON object safely
    start = raw.find("{")
    end = raw.rfind("}") + 1

    if start == -1 or end == -1:
        return Response({"error": "AI returned invalid JSON", "raw": raw}, status=500)

    json_str = raw[start:end]

    try:
        data = json.loads(json_str)
    except Exception as e:
        return Response({"error": "JSON parsing failed", "raw": raw, "details": str(e)}, status=500)

    # Fix score range
    try:
        data["score"] = max(0, min(10, int(data.get("score", 0))))
    except:
        data["score"] = 0

    # ============================================================
    # Save to DB
    # ============================================================
    InterviewResult.objects.create(
        user=user,
        session_id=session_id,
        question=question,
        answer=answer,
        score=data["score"],
        strengths=data.get("strengths", ""),
        weaknesses=data.get("weaknesses", ""),
        improved_answer=data.get("improved_answer", ""),
    )

    return Response(data)




# ============================================================
# SESSION REVIEW
# ============================================================

@api_view(["GET"])
def get_session_questions(request):
    session_id = request.GET.get("session_id")

    attempts = InterviewResult.objects.filter(
        session_id=session_id
    ).order_by("created_at")

    return Response([
        {
            "question": a.question,
            "answer": a.answer,
            "score": a.score,
            "strengths": a.strengths,
            "weaknesses": a.weaknesses,
            "improved_answer": a.improved_answer,
            "created_at": a.created_at,
        }
        for a in attempts
    ])


# ============================================================
# RESUME ANALYZER
# ============================================================

@api_view(["POST"])
def analyze_resume(request):
    if "resume" not in request.FILES:
        return Response({"error": "Upload a resume"}, status=400)

    file = request.FILES["resume"]
    text = ""

    # --- FAST PDF / DOCX READER ---
    try:
        if file.name.endswith(".pdf"):
            import fitz  # PyMuPDF (fast)
            pdf = fitz.open(stream=file.read(), filetype="pdf")
            for page in pdf:
                text += page.get_text() + "\n"

        elif file.name.endswith(".docx"):
            doc = Document(file)
            for para in doc.paragraphs:
                text += para.text + "\n"

        else:
            return Response({"error": "Unsupported file format"}, status=400)

    except Exception as e:
        return Response({"error": "Failed to read file", "details": str(e)}, status=500)

    # --- LIMIT TEXT (SPEED BOOST) ---
    text = text[:3000]  # limits AI load

    # --- STRONG AI PROMPT ---
    prompt = f"""
You are an ATS resume analysis engine. Analyze the resume below and return a DETAILED structured JSON.

Resume Text:
{text}

Your job:
- Extract maximum information.
- If something is missing, infer it intelligently.
- Do NOT leave any field empty.
- Each field must contain full, meaningful content.
- Strengths & weaknesses must be 3–4 sentences.
- Summary must be 3–5 recruiter-focused sentences.

Return ONLY valid JSON in this exact structure:

{{
    "ats_score": number,
    "best_fit_role": "string",
    "top_skills": "comma-separated string",
    "strengths": "3-4 complete sentences",
    "weaknesses": "3-4 complete sentences",
    "skills_missing": "comma-separated string",
    "summary": "3-5 detailed sentences"
}}

Rules:
- No explanations before or after the JSON.
- JSON must be complete and valid.
- Never return an empty key.
- Fill in all fields even if you must infer from context.
"""

    # --- AI MODEL CALL ---
    ai = ollama.chat(
        model="llama3.1:8b",  # better, more detailed output
        messages=[{"role": "user", "content": prompt}]
    )

    raw = ai["message"]["content"].strip()

    # --- CLEAN JSON FORMAT ---
    raw = raw.replace("```json", "").replace("```", "")

    # --- SAFE JSON PARSING ---
    try:
        cleaned = raw[raw.find("{"):raw.rfind("}") + 1]
        data = json.loads(cleaned)
    except Exception as e:
        return Response({
            "error": "AI returned invalid JSON",
            "raw_ai_output": raw,
            "exception": str(e)
        }, status=500)

    # --- SAVE SKILLS / ROLES ---
    save_role_if_new(data.get("best_fit_role", ""))

    for s in data.get("top_skills", "").split(","):
        save_skill_if_new(s.strip())

    return Response(data)


# ============================================================
# ADMIN FUNCTIONS
# ============================================================

@api_view(["POST"])
def add_question(request):
    text = request.data.get("text")
    role = request.data.get("role")
    skill = request.data.get("skill")
    level = request.data.get("level", "easy")

    if not text:
        return Response({"error": "Question text required"}, status=400)

    Question.objects.create(
        text=text,
        role=normalize(role),
        skill=normalize(skill),
        level=normalize(level),
    )

    return Response({"message": "Question added"})


@api_view(["GET"])
def list_questions(request):
    return Response(list(Question.objects.all().values()))


@api_view(["GET"])
def list_users(request):
    return Response(UserProfileSerializer(UserProfile.objects.all(), many=True).data)
