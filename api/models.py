from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    full_name = models.CharField(max_length=200)
    mobile = models.CharField(max_length=20)
    role = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.full_name


class Question(models.Model):
    text = models.TextField()
    role = models.CharField(max_length=100, blank=True)
    skill = models.CharField(max_length=100, blank=True)
    level = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.text[:50]


class InterviewResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=200, default="unknown")
    question = models.TextField()
    answer = models.TextField()
    score = models.IntegerField()
    strengths = models.TextField()
    weaknesses = models.TextField()
    improved_answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'} - {self.session_id}"
