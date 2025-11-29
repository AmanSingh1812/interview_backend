from django.urls import path
from .views import (
    register_user,
    login_user,
    get_profile,
    dashboard_stats,
    get_roles,
    get_skills,
    get_question,
    evaluate_answer,
    analyze_resume,
    add_question,
    list_questions,
    list_users,
    get_session_questions,
)

urlpatterns = [
    path("register/", register_user),
    path("login/", login_user),
    path("profile/", get_profile),
    path("dashboard/", dashboard_stats),

    # Interview Flow
    path("roles/", get_roles),
    path("skills/", get_skills),
    path("get_question/", get_question),
    path("evaluate/", evaluate_answer),

    # Resume Analyzer
    path("analyze_resume/", analyze_resume),

    # Admin
    path("admin/add-question/", add_question),
    path("admin/list-questions/", list_questions),
    path("admin/list-users/", list_users),
    path("session/questions/", get_session_questions),

]
