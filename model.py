
import streamlit as st
import google.generativeai as genai
import os
from PIL import Image
import io
import speech_recognition as sr
import re
import graphviz
import pyttsx3
import threading
import base64
import json
from datetime import datetime, timedelta
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, Circle
import numpy as np

# --- Gemini API Configuration ---
def get_api_key():
    """Get API key from user input or environment"""
    # Check if API key is already in session state
    if 'gemini_api_key' in st.session_state and st.session_state.gemini_api_key:
        return st.session_state.gemini_api_key
   
    # Check environment variables
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        st.session_state.gemini_api_key = api_key
        return api_key
   
    # Check Streamlit secrets
    try:
        st.secrets.load_if_toml_exists()
        if st.secrets.get("GEMINI_API_KEY"):
            api_key = st.secrets["GEMINI_API_KEY"]
            st.session_state.gemini_api_key = api_key
            return api_key
    except Exception:
        pass
   
    # Use fallback API key if no user key is provided
    return "AIzaSyBYy2BK8qZzqIiQGCWZ9gAAm7R8VEdbTyY"

def configure_gemini():
    """Configure Gemini API if key is available"""
    api_key = get_api_key()
    if api_key:
        try:
            genai.configure(api_key=api_key)
            return genai.GenerativeModel("gemini-2.5-flash")
        except Exception as e:
            st.error(f"Invalid API key: {e}")
            return None
    return None

# Initialize model (will be None if no API key)
model = configure_gemini()

# --- Global Session State Initialization ---
if 'users_db' not in st.session_state:
    st.session_state.users_db = {}
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'login'
if 'learning_progress_data' not in st.session_state:
    st.session_state.learning_progress_data = {
        'daily_activity': [],
        'skill_progress': {},
        'course_enrollments': [],
        'achievements': [],
        'learning_streak': 0,
        'total_study_time': 0,
        'completed_modules': 0,
        'goals_set': [],
        'goals_achieved': []
    }

# --- Utility Functions ---
def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    """Authenticate user login"""
    hashed_password = hash_password(password)
    if username in st.session_state.users_db:
        if st.session_state.users_db[username]['password'] == hashed_password:
            return True
    return False

def register_user(username, email, password):
    """Register a new user"""
    if username in st.session_state.users_db:
        return False, "Username already exists"
   
    hashed_password = hash_password(password)
    st.session_state.users_db[username] = {
        'username': username,
        'email': email,
        'password': hashed_password,
        'created_at': datetime.now().isoformat(),
        'profile': {
            'skills': [],
            'experience_level': 'Beginner',
            'bio': '',
            'learning_goals': [],
            'interests': [],
            'time_commitment': '1-5 hours',
            'learning_style': 'Visual',
            'difficulty_preference': 'Beginner-friendly',
            'onboarding_completed': False
        },
        'learning_paths': [],
        'progress': {
            'completed_modules': 0,
            'total_modules': 0,
            'learning_streak': 0,
            'achievements': [],
            'enrolled_courses': []
        }
    }
    return True, "Registration successful"

def get_file_content(file):
    """Helper: Get file content for processing"""
    if file is None:
        return ""
    try:
        if file.type == "text/plain":
            return file.getvalue().decode("utf-8")
        elif file.type in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            return f"[Uploaded file: {file.name} - content will be processed by AI]"
        elif file.type.startswith('image/'):
            return f"[Image uploaded: {file.name}]"
        else:
            return f"[Uploaded file type {file.type} not fully supported for direct text extraction, but will be used for personalization.]"
    except Exception:
        return "[Error reading file.]"

# --- Text-to-Speech Functions ---
def text_to_speech(text):
    """Convert text to speech"""
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 0.8)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        st.error(f"TTS Error: {e}")

# --- Learning Progress Tracker Class ---
class LearningProgressTracker:
    def __init__(self):
        self.initialize_progress_data()
   
    def initialize_progress_data(self):
        if 'learning_progress_data' not in st.session_state:
            st.session_state.learning_progress_data = {
                'daily_activity': [],
                'skill_progress': {},
                'course_enrollments': [],
                'achievements': [],
                'learning_streak': 0,
                'total_study_time': 0,
                'completed_modules': 0,
                'goals_set': [],
                'goals_achieved': []
            }
       
        # Ensure current user has progress data initialized
        if st.session_state.current_user and st.session_state.current_user not in st.session_state.learning_progress_data['skill_progress']:
            st.session_state.learning_progress_data['skill_progress'][st.session_state.current_user] = {}

    def log_daily_activity(self, user_id, activity_type, duration_minutes=0, details=""):
        activity = {
            'user_id': user_id,
            'date': datetime.now().date().isoformat(),
            'activity_type': activity_type,
            'duration_minutes': duration_minutes,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        st.session_state.learning_progress_data['daily_activity'].append(activity)
        self.update_learning_streak(user_id)
        return activity

    def update_learning_streak(self, user_id):
        today = datetime.now().date()
        user_activities = [a for a in st.session_state.learning_progress_data['daily_activity']
                          if a['user_id'] == user_id]
       
        if not user_activities:
            st.session_state.learning_progress_data['learning_streak'] = 0
            return 0
       
        study_dates = sorted(list(set([datetime.strptime(a['date'], '%Y-%m-%d').date() for a in user_activities if a['duration_minutes'] > 0])), reverse=True)
       
        streak = 0
        current_checking_date = today
       
        for date_obj in study_dates:
            if date_obj == current_checking_date:
                streak += 1
                current_checking_date -= timedelta(days=1)
            elif date_obj < current_checking_date:
                break
       
        st.session_state.learning_progress_data['learning_streak'] = streak
        return streak
   
    def update_skill_progress(self, user_id, skill_name, progress_percentage, experience_points=0):
        if user_id not in st.session_state.learning_progress_data['skill_progress']:
            st.session_state.learning_progress_data['skill_progress'][user_id] = {}
       
        skill_data = st.session_state.learning_progress_data['skill_progress'][user_id].get(skill_name, {
            'progress': 0,
            'experience_points': 0,
            'last_updated': datetime.now().isoformat(),
            'milestones': []
        })
       
        skill_data['progress'] = min(100, max(0, progress_percentage))
        skill_data['experience_points'] += experience_points
        skill_data['last_updated'] = datetime.now().isoformat()
       
        for threshold in [25, 50, 75, 100]:
            if skill_data['progress'] >= threshold and threshold not in [m['percentage'] for m in skill_data['milestones']]:
                skill_data['milestones'].append({'percentage': threshold, 'date': datetime.now().isoformat()})
                self.add_achievement(user_id, f"🎯 {skill_name} - {threshold}% Complete", 'skill')
       
        st.session_state.learning_progress_data['skill_progress'][user_id][skill_name] = skill_data
        return skill_data
   
    def add_achievement(self, user_id, achievement_name, achievement_type="general"):
        achievement = {
            'user_id': user_id,
            'achievement': achievement_name,
            'type': achievement_type,
            'date': datetime.now().isoformat(),
            'icon': self.get_achievement_icon(achievement_type)
        }
       
        if not any(a['user_id'] == user_id and a['achievement'] == achievement_name for a in st.session_state.learning_progress_data['achievements']):
            st.session_state.learning_progress_data['achievements'].append(achievement)
            return True
        return False

    def get_achievement_icon(self, achievement_type):
        icons = {
            'streak': '🔥', 'skill': '🏆', 'course': '📚', 'project': '🚀',
            'community': '🤝', 'milestone': '⭐', 'general': '🏅'
        }
        return icons.get(achievement_type, '🏅')
   
    def get_user_dashboard_data(self, user_id):
        user_activities = [a for a in st.session_state.learning_progress_data['daily_activity']
                          if a['user_id'] == user_id]
        user_skills = st.session_state.learning_progress_data['skill_progress'].get(user_id, {})
        user_courses = [c for c in st.session_state.learning_progress_data['course_enrollments']
                       if c['user_id'] == user_id]
        user_achievements = [a for a in st.session_state.learning_progress_data['achievements']
                           if a['user_id'] == user_id]
        user_goals = [g for g in st.session_state.learning_progress_data['goals_set']
                     if g['user_id'] == user_id]
       
        return {
            'activities': user_activities,
            'skills': user_skills,
            'courses': user_courses,
            'achievements': user_achievements,
            'goals': user_goals,
            'learning_streak': st.session_state.learning_progress_data['learning_streak'],
            'total_study_time': sum(a['duration_minutes'] for a in user_activities),
            'completed_modules': len([a for a in user_activities if a['activity_type'] == 'course'])
        }
   
    def create_progress_charts(self, user_id):
        dashboard_data = self.get_user_dashboard_data(user_id)
        charts = {}

        if dashboard_data['activities']:
            activity_df = pd.DataFrame(dashboard_data['activities'])
            activity_df['date'] = pd.to_datetime(activity_df['date'])
            daily_study_time = activity_df.groupby('date')['duration_minutes'].sum().reset_index()
            fig_activity = px.line(daily_study_time, x='date', y='duration_minutes',
                                   title='Daily Study Time (Minutes)',
                                   labels={'duration_minutes': 'Study Time (min)', 'date': 'Date'})
            fig_activity.update_layout(height=300, margin=dict(t=50, b=0, l=0, r=0))
            charts['daily_activity'] = fig_activity
           
        if dashboard_data['skills']:
            skills_df = pd.DataFrame([
                {'skill': skill, 'progress': data['progress']}
                for skill, data in dashboard_data['skills'].items()
            ])
            if not skills_df.empty:
                fig_skills = px.bar(skills_df, x='skill', y='progress',
                                    title='Skills Progress',
                                    labels={'progress': 'Progress (%)', 'skill': 'Skill'})
                fig_skills.update_layout(height=300, margin=dict(t=50, b=0, l=0, r=0))
                charts['skills_progress'] = fig_skills
           
        if dashboard_data['courses']:
            courses_df = pd.DataFrame(dashboard_data['courses'])
            if not courses_df.empty:
                fig_courses = px.pie(courses_df, values='progress', names='course_name',
                                     title='Course Progress')
                fig_courses.update_layout(height=300, margin=dict(t=50, b=0, l=0, r=0))
                charts['course_progress'] = fig_courses
           
        return charts
   
    def get_learning_insights(self, user_id):
        dashboard_data = self.get_user_dashboard_data(user_id)
        insights = []
       
        streak = dashboard_data['learning_streak']
        if streak >= 7:
            insights.append(f"🔥 Amazing! You have a {streak}-day learning streak!")
        elif streak >= 3:
            insights.append(f"🔥 Great job! Keep up your {streak}-day streak!")
        else:
            insights.append("💪 Start a learning streak today!")
       
        if dashboard_data['skills']:
            top_skill = max(dashboard_data['skills'].items(), key=lambda x: x[1]['progress'])
            insights.append(f"🏆 Your strongest skill: {top_skill[0]} ({top_skill[1]['progress']}%)")
           
            if len(dashboard_data['skills']) < 3:
                insights.append("💡 Consider exploring more skills to diversify your profile")
       
        active_courses = [c for c in dashboard_data['courses'] if c['status'] == 'Active']
        if len(active_courses) > 3:
            insights.append("📚 You have many active courses. Focus on completing one at a time!")
        elif len(active_courses) == 0:
            insights.append("🎯 Ready to start a new course? Check out the learning paths!")
       
        active_goals = [g for g in dashboard_data['goals'] if g['status'] == 'Active']
        if len(active_goals) == 0:
            insights.append("🎯 Set some learning goals to stay motivated!")
       
        return insights

# Initialize progress tracker
progress_tracker = LearningProgressTracker()

# --- Backend Integration for Learning Paths ---
def generate_basic_learning_path(user_profile, goal, additional_skills="", preferences="", resume_content="", use_previous_skills=True):
    """Generate a basic learning path without AI"""
   
    experience_level = user_profile.get('experience_level', 'Beginner')
    skills = user_profile.get('skills', [])
    time_commitment = user_profile.get('time_commitment', '1-5 hours')
   
    if use_previous_skills and skills:
        path_intro = f"Since you have experience with {', '.join(skills[:3])}, we'll build on your existing knowledge."
    else:
        path_intro = "Starting fresh with foundational concepts."
   
    basic_path = f"""
# 🎯 Learning Path: {goal}

## 📋 Overview
{path_intro}
- *Experience Level*: {experience_level}
- *Time Commitment*: {time_commitment}
- *Goal*: {goal}

## 🛤 Learning Roadmap

### Phase 1: Foundation (Weeks 1-4)
- *Week 1-2*: Learn the basics and fundamentals
  - Start with introductory concepts
  - Set up your learning environment
  - Complete basic tutorials

- *Week 3-4*: Build initial understanding
  - Practice with simple exercises
  - Join relevant communities
  - Begin your first small project

### Phase 2: Intermediate (Weeks 5-8)
- *Week 5-6*: Deeper learning
  - Advanced concepts and techniques
  - Hands-on practice sessions
  - Work on intermediate projects

- *Week 7-8*: Practical application
  - Build real-world projects
  - Collaborate with others
  - Document your learning

### Phase 3: Advanced (Weeks 9-12)
- *Week 9-10*: Specialization
  - Focus on specific areas of interest
  - Advanced techniques and best practices
  - Contribute to open-source projects

- *Week 11-12*: Mastery preparation
  - Complex projects and challenges
  - Teaching others what you've learned
  - Prepare for certification or portfolio

## 📚 Recommended Resources

### Free Online Courses
- *Coursera*: [Search for "{goal}" courses](https://www.coursera.org/)
- *edX*: [Browse relevant programs](https://www.edx.org/)
- *freeCodeCamp*: [Free coding curriculum](https://www.freecodecamp.org/)
- *Khan Academy*: [Foundation concepts](https://www.khanacademy.org/)

### Practice Platforms
- *GitHub*: [Create projects and collaborate](https://github.com/)
- *LeetCode*: [Practice coding problems](https://leetcode.com/)
- *HackerRank*: [Skill assessments](https://www.hackerrank.com/)

### Communities & Support
- *Reddit*: [r/learnprogramming](https://reddit.com/r/learnprogramming)
- *Stack Overflow*: [Get help with specific questions](https://stackoverflow.com/)
- *Discord*: [Join learning communities](https://discord.com/)

## 🎯 Projects & Milestones

### Mini Projects (Weeks 2-4)
1. *Hello World Project*: Create your first simple project
2. *Tutorial Project*: Follow a step-by-step tutorial
3. *Personal Project*: Build something you're interested in

### Portfolio Projects (Weeks 6-8)
1. *Intermediate Project*: Something that demonstrates your skills
2. *Collaborative Project*: Work with others on a project
3. *Open Source Contribution*: Contribute to an existing project

### Advanced Projects (Weeks 10-12)
1. *Capstone Project*: A comprehensive project showcasing your skills
2. *Teaching Project*: Create content to help others learn
3. *Certification Project*: Prepare for relevant certifications

## 📊 Progress Tracking

### Weekly Checkpoints
- *Monday*: Set weekly goals
- *Wednesday*: Mid-week progress review
- *Friday*: Reflect on what you learned
- *Sunday*: Plan next week's focus

### Monthly Milestones
- *Month 1*: Complete foundation phase
- *Month 2*: Finish intermediate projects
- *Month 3*: Achieve advanced competency

## 💡 Tips for Success

1. *Consistency*: Study regularly, even if just for 30 minutes
2. *Practice*: Apply what you learn immediately
3. *Community*: Join forums and ask questions
4. *Projects*: Build real things, not just follow tutorials
5. *Documentation*: Keep a learning journal
6. *Networking*: Connect with others in your field

## 🎉 Next Steps

1. *Start Today*: Begin with the first week's activities
2. *Set Reminders*: Schedule regular study time
3. *Join Communities*: Find your learning tribe
4. *Track Progress*: Use this platform to log your activities
5. *Stay Motivated*: Celebrate small wins along the way

---

💡 **Pro Tip: For AI-powered personalized learning paths, add your Gemini API key in the settings!
"""
   
    return {
        'success': True,
        'learning_path': basic_path,
        'generated_at': datetime.now().isoformat(),
        'goal': goal,
        'ai_generated': False
    }

def generate_learning_path_ai(user_profile, goal, additional_skills="", preferences="", resume_content="", use_previous_skills=True):
    """Generate personalized learning path using Gemini AI"""
   
    if not model:
        return generate_detailed_career_path(user_profile, goal, use_previous_skills)
   
    SYSTEM_PROMPT = ("You are an expert learning path generator. "
                     "Create a comprehensive, personalized learning path based on the user's profile and request. "
                     "Focus on actionable steps, open-source resources with direct links, and clear milestones. "
                     "Make it encouraging and inspiring.")

    skill_strategy = ("Leverage the user's existing skills and experience to accelerate the path, suggest bridge modules to transition into the goal area, and skip fundamentals they likely know."
                     if use_previous_skills else
                     "Assume the user is starting fresh or wants a new direction. Start from foundations with a clean, beginner-friendly path, with optional notes where prior experience could help but do not rely on it.")

    prompt = f"""
    {SYSTEM_PROMPT}

    USER PROFILE:
    - Experience Level: {user_profile.get('experience_level', 'Beginner')}
    - Current Skills: {', '.join(user_profile.get('skills', []))}
    - Learning Goals: {', '.join(user_profile.get('learning_goals', []))}
    - Interests: {', '.join(user_profile.get('interests', []))}
    - Time Commitment: {user_profile.get('time_commitment', 'Not specified')}
    - Learning Style: {user_profile.get('learning_style', 'Mixed')}
    - Difficulty Preference: {user_profile.get('difficulty_preference', 'Mixed')}

    LEARNING REQUEST:
    - Primary Goal: {goal}
    - Additional Skills: {additional_skills}
    - Preferences: {preferences}
    - Resume/Background: {resume_content}
    - Use Previous Skills: {use_previous_skills}

    Please generate a detailed learning path that includes:

    1. *OVERVIEW & ASSESSMENT*
       - Current skill assessment relative to goal
       - Goal breakdown into smaller, manageable targets
       - Estimated timeline for completion
       - Difficulty progression plan

    2. *LEARNING ROADMAP* (Step-by-step with estimated time for each)
       - Phase 1: Foundation (essential concepts, tools, initial projects)
       - Phase 2: Intermediate (deeper dives, practical applications, guided projects)
       - Phase 3: Advanced (complex topics, real-world case studies, portfolio projects)
       - Phase 4: Mastery (specialization, contribution, continuous learning strategies)

    3. *OPEN SOURCE LEARNING RESOURCES* (with direct links - provide at least 3 for each category)
       - Free online courses (e.g., Coursera, edX, freeCodeCamp)
       - Documentation and tutorials (e.g., MDN, official docs)
       - Practice platforms (e.g., LeetCode, HackerRank, Kaggle)
       - Community forums/blogs (e.g., Stack Overflow, Reddit, Dev.to)

    4. *PROJECTS & PRACTICAL WORK*
       - Suggested mini-projects for each phase
       - Ideas for portfolio-worthy projects
       - Advice on collaborative projects

    5. *CHECKPOINTS & MILESTONES*
       - How to track weekly/monthly progress
       - Self-assessment techniques
       - Strategies for staying motivated

    6. *COMMUNITY & SUPPORT*
       - Recommended online communities
       - Tips for finding mentors
       - Study group ideas

    Format the response with clear headings, bullet points, and actionable steps.
    Make it motivating and personalized to the user's profile.

    SPECIAL INSTRUCTION ABOUT PRIOR SKILLS:
    {skill_strategy}
    """
   
    try:
        response = model.generate_content(prompt)
        if hasattr(response, "text") and response.text:
            return {
                'success': True,
                'learning_path': response.text,
                'generated_at': datetime.now().isoformat(),
                'goal': goal
            }
        else:
            return {
                'success': False,
                'error': 'Could not generate learning path'
            }
           
    except Exception as e:
        return {
            'success': False,
            'error': f'Error generating learning path: {str(e)}'
        }

def generate_learning_path_flowchart(user_profile, goal, use_previous_skills=True):
    """Generate a visual learning path flowchart with clear, concise wording related to exact path"""
   
    try:
        # Get user-specific information for personalized flowchart
        experience_level = user_profile.get('experience_level', 'Beginner')
        skills = user_profile.get('skills', [])
        time_commitment = user_profile.get('time_commitment', '1-5 hours')
       
        # Create figure with black background
        fig, ax = plt.subplots(1, 1, figsize=(16, 10))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_facecolor('#000000')  # Black background
        fig.patch.set_facecolor('#000000')
       
        # Create winding road path
        road_x = np.linspace(0.05, 0.95, 100)
        road_y = 0.4 + 0.3 * np.sin(2 * np.pi * road_x) + 0.1 * np.sin(8 * np.pi * road_x)
       
        # Draw main road (white)
        ax.plot(road_x, road_y, color='white', linewidth=8, alpha=0.9, solid_capstyle='round')
       
        # Draw dashed center line
        ax.plot(road_x, road_y, color='white', linewidth=2, alpha=0.6, linestyle='--')
       
        # Add arrow at the end
        arrow_x, arrow_y = 0.95, road_y[-1]
        ax.annotate('', xy=(arrow_x+0.03, arrow_y), xytext=(arrow_x, arrow_y),
                   arrowprops=dict(arrowstyle='->', lw=4, color='white'))
       
        # Define personalized learning path steps based on goal and user profile
        if 'data' in goal.lower() or 'analyst' in goal.lower():
            steps = [
                {
                    "title": "Data Fundamentals",
                    "description": f"Master {experience_level} data concepts & tools",
                    "color": "#3B82F6",  # Blue
                    "position": (0.1, 0.8),
                    "icon": "📊"
                },
                {
                    "title": "Analytics Skills",
                    "description": "Build statistical & visualization expertise",
                    "color": "#10B981",  # Green
                    "position": (0.3, 0.6),
                    "icon": "📈"
                },
                {
                    "title": "AI Integration",
                    "description": "Leverage AI for advanced data insights",
                    "color": "#10B981",  # Green
                    "position": (0.5, 0.8),
                    "icon": "🤖"
                },
                {
                    "title": "Portfolio Projects",
                    "description": "Create data-driven project showcase",
                    "color": "#F59E0B",  # Yellow
                    "position": (0.7, 0.6),
                    "icon": "💼"
                },
                {
                    "title": "Data Professional",
                    "description": "Ready for {goal} role",
                    "color": "#F97316",  # Orange
                    "position": (0.9, 0.8),
                    "icon": "🎯"
                }
            ]
        elif 'developer' in goal.lower() or 'engineer' in goal.lower() or 'programming' in goal.lower():
            steps = [
                {
                    "title": "Code Foundation",
                    "description": f"Learn {experience_level} programming basics",
                    "color": "#3B82F6",  # Blue
                    "position": (0.1, 0.8),
                    "icon": "💻"
                },
                {
                    "title": "Framework Mastery",
                    "description": "Build expertise in key technologies",
                    "color": "#10B981",  # Green
                    "position": (0.3, 0.6),
                    "icon": "⚙️"
                },
                {
                    "title": "AI Development",
                    "description": "Integrate AI tools in development workflow",
                    "color": "#10B981",  # Green
                    "position": (0.5, 0.8),
                    "icon": "🤖"
                },
                {
                    "title": "Project Showcase",
                    "description": "Build impressive development portfolio",
                    "color": "#F59E0B",  # Yellow
                    "position": (0.7, 0.6),
                    "icon": "🚀"
                },
                {
                    "title": "Senior Developer",
                    "description": "Ready for {goal} position",
                    "color": "#F97316",  # Orange
                    "position": (0.9, 0.8),
                    "icon": "🎯"
                }
            ]
        elif 'design' in goal.lower() or 'ui' in goal.lower() or 'ux' in goal.lower():
            steps = [
                {
                    "title": "Design Principles",
                    "description": f"Master {experience_level} design fundamentals",
                    "color": "#3B82F6",  # Blue
                    "position": (0.1, 0.8),
                    "icon": "🎨"
                },
                {
                    "title": "Tool Proficiency",
                    "description": "Master industry-standard design tools",
                    "color": "#10B981",  # Green
                    "position": (0.3, 0.6),
                    "icon": "🛠️"
                },
                {
                    "title": "AI Design Tools",
                    "description": "Enhance creativity with AI assistance",
                    "color": "#10B981",  # Green
                    "position": (0.5, 0.8),
                    "icon": "🤖"
                },
                {
                    "title": "Design Portfolio",
                    "description": "Create stunning visual portfolio",
                    "color": "#F59E0B",  # Yellow
                    "position": (0.7, 0.6),
                    "icon": "📱"
                },
                {
                    "title": "Design Professional",
                    "description": "Ready for {goal} career",
                    "color": "#F97316",  # Orange
                    "position": (0.9, 0.8),
                    "icon": "🎯"
                }
            ]
        else:
            # Generic professional path
            steps = [
                {
                    "title": "Core Knowledge",
                    "description": f"Build {experience_level} expertise foundation",
                    "color": "#3B82F6",  # Blue
                    "position": (0.1, 0.8),
                    "icon": "📚"
                },
                {
                    "title": "Skill Development",
                    "description": "Develop specialized competencies",
                    "color": "#10B981",  # Green
                    "position": (0.3, 0.6),
                    "icon": "🛠️"
                },
                {
                    "title": "AI Enhancement",
                    "description": "Leverage AI for professional growth",
                    "color": "#10B981",  # Green
                    "position": (0.5, 0.8),
                    "icon": "🤖"
                },
                {
                    "title": "Professional Portfolio",
                    "description": "Showcase achievements & projects",
                    "color": "#F59E0B",  # Yellow
                    "position": (0.7, 0.6),
                    "icon": "💼"
                },
                {
                    "title": "Career Success",
                    "description": "Achieve {goal} professional status",
                    "color": "#F97316",  # Orange
                    "position": (0.9, 0.8),
                    "icon": "🎯"
                }
            ]
       
        # Draw each step
        for i, step in enumerate(steps):
            x, y = step["position"]
           
            # Draw circle for step
            circle = Circle((x, y), 0.08, facecolor=step["color"], edgecolor='white',
                           linewidth=2, alpha=0.9, zorder=10)
            ax.add_patch(circle)
           
            # Add icon inside circle
            ax.text(x, y, step["icon"], fontsize=20, ha='center', va='center',
                   weight='bold', zorder=11, color='white')
           
            # Add title below circle
            ax.text(x, y-0.15, step["title"], fontsize=12, ha='center', va='center',
                   color='white', weight='bold', bbox=dict(boxstyle="round,pad=0.3",
                   facecolor='black', alpha=0.7), zorder=9)
           
            # Add description below title
            ax.text(x, y-0.22, step["description"], fontsize=9, ha='center', va='center',
                   color='white', bbox=dict(boxstyle="round,pad=0.2",
                   facecolor='black', alpha=0.5), zorder=9)
           
            # Add step number
            ax.text(x, y+0.12, f"{i+1}", fontsize=14, ha='center', va='center',
                   color='white', weight='bold', bbox=dict(boxstyle="circle",
                   facecolor=step["color"], alpha=0.8), zorder=9)
       
        # Add main title
        ax.text(0.5, 0.95, "Learning Path Journey", fontsize=24, ha='center',
               va='center', color='white', weight='bold')
       
        # Add subtitle with goal
        ax.text(0.5, 0.9, f"Path to: {goal}", fontsize=16, ha='center', va='center',
               color='#94A3B8', style='italic')
       
        # Remove axes
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
       
        plt.tight_layout()
       
        # Convert to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='#000000')
        buf.seek(0)
        img_bytes = buf.getvalue()
        buf.close()
        plt.close()
       
        return img_bytes
       
    except Exception as e:
        st.error(f"Error generating learning path flowchart: {e}")
        return None

def generate_career_readiness_flowchart(user_profile, goal, use_previous_skills=True):
    """Generate a career readiness flowchart matching the provided image exactly"""
   
    try:
        # Create figure with black background
        fig, ax = plt.subplots(1, 1, figsize=(16, 10))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_facecolor('#000000')  # Black background
        fig.patch.set_facecolor('#000000')
       
        # Create winding road path
        road_x = np.linspace(0.05, 0.95, 100)
        road_y = 0.4 + 0.3 * np.sin(2 * np.pi * road_x) + 0.1 * np.sin(8 * np.pi * road_x)
       
        # Draw main road (white)
        ax.plot(road_x, road_y, color='white', linewidth=8, alpha=0.9, solid_capstyle='round')
       
        # Draw dashed center line
        ax.plot(road_x, road_y, color='white', linewidth=2, alpha=0.6, linestyle='--')
       
        # Add arrow at the end
        arrow_x, arrow_y = 0.95, road_y[-1]
        ax.annotate('', xy=(arrow_x+0.03, arrow_y), xytext=(arrow_x, arrow_y),
                   arrowprops=dict(arrowstyle='->', lw=4, color='white'))
       
        # Define steps exactly as in the image
        steps = [
            {
                "title": "Identify Skills",
                "description": "Determine the specific skills needed for the desired career path.",
                "color": "#3B82F6",  # Blue
                "position": (0.1, 0.8),
                "icon": "🎯"
            },
            {
                "title": "Career Path Resources",
                "description": "Access and utilize resources that outline the career path.",
                "color": "#10B981",  # Green
                "position": (0.3, 0.6),
                "icon": "📚"
            },
            {
                "title": "AI Adoption",
                "description": "Integrate AI tools and tracking to enhance learning.",
                "color": "#10B981",  # Green
                "position": (0.5, 0.8),
                "icon": "🤖"
            },
            {
                "title": "Resume Creation",
                "description": "Develop a professional resume showcasing acquired skills.",
                "color": "#F59E0B",  # Yellow
                "position": (0.7, 0.6),
                "icon": "📄"
            },
            {
                "title": "Visual Dashboard",
                "description": "Create a dashboard to track progress and visualize skills.",
                "color": "#F97316",  # Orange
                "position": (0.9, 0.8),
                "icon": "📊"
            }
        ]
       
        # Draw each step
        for i, step in enumerate(steps):
            x, y = step["position"]
           
            # Draw circle for step
            circle = Circle((x, y), 0.08, facecolor=step["color"], edgecolor='white',
                           linewidth=2, alpha=0.9, zorder=10)
            ax.add_patch(circle)
           
            # Add icon inside circle
            ax.text(x, y, step["icon"], fontsize=20, ha='center', va='center',
                   weight='bold', zorder=11, color='white')
           
            # Add title below circle
            ax.text(x, y-0.15, step["title"], fontsize=12, ha='center', va='center',
                   color='white', weight='bold', bbox=dict(boxstyle="round,pad=0.3",
                   facecolor='black', alpha=0.7), zorder=9)
           
            # Add description below title
            ax.text(x, y-0.22, step["description"], fontsize=9, ha='center', va='center',
                   color='white', bbox=dict(boxstyle="round,pad=0.2",
                   facecolor='black', alpha=0.5), zorder=9)
           
            # Add step number
            ax.text(x, y+0.12, f"{i+1}", fontsize=14, ha='center', va='center',
                   color='white', weight='bold', bbox=dict(boxstyle="circle",
                   facecolor=step["color"], alpha=0.8), zorder=9)
       
        # Add main title
        ax.text(0.5, 0.95, "Achieving Career Readiness", fontsize=24, ha='center',
               va='center', color='white', weight='bold')
       
        # Add subtitle with goal
        ax.text(0.5, 0.9, f"Path to: {goal}", fontsize=16, ha='center', va='center',
               color='#94A3B8', style='italic')
       
        # Remove axes
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
       
        plt.tight_layout()
       
        # Convert to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', facecolor='#000000')
        buf.seek(0)
        img_bytes = buf.getvalue()
        buf.close()
        plt.close()
       
        return img_bytes
       
    except Exception as e:
        st.error(f"Error generating flowchart: {e}")
        return None

def generate_creative_resume_template(template_type, user_data, goal):
    """Generate different creative resume templates"""
   
    templates = {
        "modern_minimal": {
            "header_style": "Clean, minimal design with subtle gradients",
            "color_scheme": "Monochromatic with accent colors",
            "layout": "Single column with lots of white space",
            "typography": "Clean sans-serif fonts"
        },
        "creative_colorful": {
            "header_style": "Bold, colorful design with geometric shapes",
            "color_scheme": "Vibrant colors with gradients",
            "layout": "Two-column with creative sidebar",
            "typography": "Mix of modern and creative fonts"
        },
        "professional_elegant": {
            "header_style": "Elegant design with sophisticated styling",
            "color_scheme": "Professional blues and grays",
            "layout": "Traditional with modern touches",
            "typography": "Classic serif and modern sans-serif"
        },
        "tech_innovative": {
            "header_style": "Tech-focused with digital elements",
            "color_scheme": "Dark themes with neon accents",
            "layout": "Grid-based with tech elements",
            "typography": "Modern tech fonts"
        }
    }
   
    return templates.get(template_type, templates["modern_minimal"])

def generate_ai_resume(user_profile, learning_paths, goal):
    """Generate creative and unique AI-powered resume based on user skills and learning paths"""
   
    if not model:
        return "AI resume generation requires a Gemini API key. Please add your API key in the settings."
   
    try:
        # Get user skills and experience
        skills = user_profile.get('skills', [])
        experience_level = user_profile.get('experience_level', 'Beginner')
        bio = user_profile.get('bio', '')
        interests = user_profile.get('interests', [])
        learning_goals = user_profile.get('learning_goals', [])
       
        # Get learning path information - ensure learning_paths is a list
        path_info = ""
        if learning_paths and isinstance(learning_paths, list) and len(learning_paths) > 0:
            latest_path = learning_paths[-1]  # Get most recent path
            if isinstance(latest_path, dict):
                path_info = f"Learning Path: {latest_path.get('goal', goal)}"
                if 'path' in latest_path and isinstance(latest_path['path'], dict):
                    path_info += f"\nSkills to develop: {', '.join(latest_path['path'].get('skills', []))}"
            else:
                path_info = f"Learning Path: {goal}"
       
        # Create comprehensive prompt for creative resume generation
        resume_prompt = f"""
        Create a CREATIVE, VISUAL, and CONCISE professional resume for {st.session_state.current_user}. Make it SHORT, IMPACTFUL, and VISUALLY STUNNING - NOT like an essay or abstract.

        PERSONAL INFORMATION:
        - Name: {st.session_state.current_user}
        - Email: {user_profile.get('email', 'email@example.com')}
        - Skills: {', '.join(skills) if skills else 'General professional skills'}
        - Experience Level: {experience_level}
        - Bio: {bio}
        - Career Goal: {goal}
        - Learning Goals: {', '.join(learning_goals)}
        - Interests: {', '.join(interests)}
        - Time Commitment: {user_profile.get('time_commitment', 'Not specified')}
        - Learning Style: {user_profile.get('learning_style', 'Mixed')}
       
        {path_info}
       
        CRITICAL REQUIREMENTS:
        - KEEP IT SHORT AND SWEET - Maximum 1 page
        - Use BULLET POINTS, not paragraphs
        - Make it VISUAL and CREATIVE
        - Use POWER WORDS and ACTION VERBS
        - Include NUMBERS and METRICS
        - Make it SCANNABLE in 30 seconds
       
        CREATIVE DESIGN ELEMENTS:
        - Use creative section headers with symbols/emojis
        - Include visual separators and formatting
        - Use color coding suggestions
        - Add creative layout descriptions
        - Include unique visual elements
       
        CONTENT STRUCTURE (KEEP CONCISE):
        1. **HEADER**: Name + Title + Contact (with icons)
        2. **PROFESSIONAL SUMMARY**: 2-3 POWERFUL sentences max
        3. **CORE SKILLS**: 3-4 categories with 3-4 skills each
        4. **EXPERIENCE**: 2-3 roles with 3-4 bullet points each
        5. **PROJECTS**: 2-3 projects with 2-3 bullet points each
        6. **EDUCATION**: Degrees + certifications (brief)
        7. **ACHIEVEMENTS**: Key accomplishments (bullet points)
       
        WRITING STYLE:
        - Use SHORT, PUNCHY sentences
        - Start with ACTION VERBS (Led, Developed, Created, Achieved)
        - Include NUMBERS (increased by 25%, managed 10+ projects)
        - Use POWER WORDS (innovative, strategic, impactful)
        - NO long paragraphs or explanations
        - Make every word COUNT
       
        CREATIVITY REQUIREMENTS:
        - Use creative section titles (not boring "Experience")
        - Add visual formatting suggestions
        - Include unique achievements
        - Make it MEMORABLE and DISTINCTIVE
        - Add personality without being unprofessional
        - Use industry-specific terminology
        - Include soft skills creatively
       
        EXAMPLES OF GOOD FORMATTING:
        ✨ PROFESSIONAL HIGHLIGHTS ✨
        🚀 CAREER JOURNEY 🚀
        💡 INNOVATION & ACHIEVEMENTS 💡
        🛠️ TECHNICAL MASTERY 🛠️
        🎯 PROJECT SHOWCASE 🎯
       
        Generate a CREATIVE, CONCISE, and VISUALLY APPEALING resume that stands out. Make it SHORT, IMPACTFUL, and SCANNABLE - NOT an essay!
        """
       
        response = model.generate_content(resume_prompt)
        return response.text if response.text else "Error generating resume content."
       
    except Exception as e:
        return f"Error generating resume: {e}"

def generate_detailed_career_path(user_profile, goal, use_previous_skills=True):
    """Generate detailed career path with specific steps and resources for any field"""
   
    experience_level = user_profile.get('experience_level', 'Beginner')
    skills = user_profile.get('skills', [])
    time_commitment = user_profile.get('time_commitment', '1-5 hours')
   
    if use_previous_skills and skills:
        path_intro = f"Building on your existing skills: {', '.join(skills[:3])}"
        current_skills_text = f"Current Skills: {', '.join(skills)}"
    else:
        path_intro = "Starting fresh with foundational concepts - no prior experience assumed"
        current_skills_text = "Current Skills: None (Starting from basics)"
   
    # Determine field-specific resources based on goal
    field_resources = get_field_specific_resources(goal)
   
    detailed_path = f"""
# 🎯 Career Readiness Path: {goal}

## 📋 Career Readiness Overview
{path_intro}
- *Target Role*: {goal}
- *Experience Level*: {experience_level}
- *Time Commitment*: {time_commitment}
- *{current_skills_text}*

---

## 🛤 Career Readiness Roadmap

### Step 1: 🎯 Identify Required Skills
*Objective*: Determine the specific skills needed for your target career

*Actions*:
- Research job postings for {goal} positions
- Identify {field_resources['field'].lower()} skills (industry-specific tools, methodologies, frameworks)
- List soft skills (communication, leadership, problem-solving, teamwork)
- Analyze skill gaps between current and required skills
- *For Fresh Start*: Focus on fundamental concepts and entry-level requirements

*Resources*:
- *Job Sites*: {', '.join(field_resources['job_sites'][:3])}
- *Career Insights*: Industry-specific career guides and salary data
- *Professional Networks*: LinkedIn, industry associations, and professional groups

*Deliverable*: Skills gap analysis document

---

### Step 2: 📚 Access Career Path Resources
*Objective*: Gather learning resources and create a structured study plan

*Actions*:
- Curate {field_resources['field'].lower()} learning materials (courses, books, tutorials, workshops)
- Create a study schedule based on your time commitment
- Join relevant {field_resources['field'].lower()} professional communities
- Set up learning environment and industry-specific tools
- *For Fresh Start*: Start with beginner-friendly resources and foundational courses

*Resources*:
- *Learning Platforms*: {', '.join(field_resources['learning_platforms'][:3])}
- *Professional Communities*: {', '.join(field_resources['communities'][:3])}
- *Field-Specific Resources*: Industry documentation, professional associations, specialized platforms

*Deliverable*: Personal learning roadmap with timeline

---

### Step 3: 🤖 AI-Powered Learning Enhancement
*Objective*: Integrate AI tools to accelerate and track your learning progress

*Actions*:
- Use AI assistants for {field_resources['field'].lower()} help and explanations
- Implement progress tracking with AI-powered insights
- Leverage AI for personalized learning recommendations
- Automate routine tasks to focus on learning

*AI Tools*:
- *Field Assistance*: ChatGPT, Claude, Gemini for {field_resources['field'].lower()} guidance
- *Learning Platforms*: AI-enhanced courses and personalized learning paths
- *Progress Tracking*: This platform's AI-powered analytics
- *Research*: AI-powered research tools for staying updated with {field_resources['field'].lower()} trends

*Deliverable*: AI-enhanced learning setup and tracking system

---

### Step 4: 📄 Professional Resume Creation
*Objective*: Develop a compelling resume that showcases your acquired skills

*Actions*:
- Write compelling resume sections highlighting {field_resources['field'].lower()} skills
- Create a professional portfolio showcasing {field_resources['field'].lower()} projects and achievements
- Optimize resume for ATS (Applicant Tracking Systems) with industry keywords
- Prepare cover letters tailored to specific {field_resources['field'].lower()} positions

*Resources*:
- *Portfolio Platforms*: {', '.join(field_resources['portfolios'][:3])}
- *Resume Builders*: Canva, Resume.io, field-specific templates
- *ATS Optimization*: Jobscan, Resume Worded, industry-specific keywords

*Deliverable*: Professional resume and portfolio

---

### Step 5: 📊 Visual Progress Dashboard
*Objective*: Create a comprehensive dashboard to track and visualize your career readiness progress

*Actions*:
- Set up progress tracking for each {field_resources['field'].lower()} skill
- Create visual representations of your {field_resources['field'].lower()} learning journey
- Monitor milestones and achievements in your field
- Generate reports showcasing your {field_resources['field'].lower()} expertise

*Dashboard Features*:
- *Skill Progress*: Visual progress bars for each skill
- *Learning Streak*: Daily learning consistency tracking
- *Project Portfolio*: Showcase completed projects
- *Achievement Badges*: Gamified learning milestones
- *Career Readiness Score*: Overall readiness assessment

*Deliverable*: Interactive career readiness dashboard

---

## 🎯 Success Metrics & Milestones

### Week 1-2: Foundation
- [ ] Complete {field_resources['field'].lower()} skills gap analysis
- [ ] Set up {field_resources['field'].lower()} learning environment
- [ ] Join 3+ {field_resources['field'].lower()} professional communities
- [ ] Create initial study schedule

### Week 3-4: Learning Acceleration
- [ ] Complete first major {field_resources['field'].lower()} course/project
- [ ] Build first {field_resources['field'].lower()} portfolio project
- [ ] Start networking in {field_resources['field'].lower()} professional communities
- [ ] Set up AI learning tools

### Week 5-6: Skill Building
- [ ] Complete 2-3 {field_resources['field'].lower()} projects
- [ ] Update resume with new {field_resources['field'].lower()} skills
- [ ] Create professional {field_resources['field'].lower()} portfolio
- [ ] Begin job application process

### Week 7-8: Career Readiness
- [ ] Finalize {field_resources['field'].lower()} resume and portfolio
- [ ] Complete career readiness dashboard
- [ ] Apply to 10+ relevant {field_resources['field'].lower()} positions
- [ ] Prepare for {field_resources['field'].lower()} interviews

---

## 🚀 Next Steps

1. *Start Today*: Begin with Step 1 - skills identification
2. *Set Reminders*: Schedule daily learning time
3. *Track Progress*: Use this platform's dashboard
4. *Stay Consistent*: Follow your learning schedule
5. *Network Actively*: Engage with professional communities

---

💡 **Pro Tip: For AI-powered personalized guidance at each step, add your Gemini API key in the Profile settings!
"""
   
    return {
        'success': True,
        'learning_path': detailed_path,
        'generated_at': datetime.now().isoformat(),
        'goal': goal,
        'ai_generated': False,
        'career_readiness': True
    }

def get_field_specific_resources(goal):
    """Get field-specific resources based on career goal"""
   
    goal_lower = goal.lower()
   
    # Technology/Software fields
    if any(keyword in goal_lower for keyword in ['software', 'developer', 'programmer', 'engineer', 'coding', 'data science', 'ai', 'machine learning', 'web', 'mobile', 'cybersecurity', 'devops']):
        return {
            'field': 'Technology',
            'job_sites': ['LinkedIn', 'Indeed', 'Glassdoor', 'AngelList', 'Stack Overflow Jobs'],
            'learning_platforms': ['Coursera', 'edX', 'freeCodeCamp', 'Codecademy', 'Udemy', 'Pluralsight'],
            'communities': ['GitHub', 'Stack Overflow', 'Reddit r/programming', 'Dev.to', 'Hacker News'],
            'certifications': ['AWS', 'Google Cloud', 'Microsoft Azure', 'CompTIA', 'Cisco'],
            'portfolios': ['GitHub', 'GitLab', 'Bitbucket', 'CodePen', 'Replit']
        }
   
    # Business/Management fields
    elif any(keyword in goal_lower for keyword in ['business', 'management', 'marketing', 'sales', 'consultant', 'analyst', 'manager', 'director', 'ceo', 'entrepreneur']):
        return {
            'field': 'Business',
            'job_sites': ['LinkedIn', 'Indeed', 'Glassdoor', 'AngelList', 'Built In'],
            'learning_platforms': ['Coursera', 'edX', 'Harvard Business School Online', 'Kellogg School', 'Wharton Online'],
            'communities': ['LinkedIn Groups', 'Reddit r/business', 'Harvard Business Review', 'Forbes', 'Inc.com'],
            'certifications': ['PMP', 'Six Sigma', 'Google Analytics', 'HubSpot', 'Salesforce'],
            'portfolios': ['LinkedIn', 'Personal Website', 'Medium', 'Behance', 'Dribbble']
        }
   
    # Default/General career path
    else:
        return {
            'field': 'General',
            'job_sites': ['LinkedIn', 'Indeed', 'Glassdoor', 'Monster', 'CareerBuilder'],
            'learning_platforms': ['Coursera', 'edX', 'LinkedIn Learning', 'Udemy', 'Skillshare'],
            'communities': ['LinkedIn', 'Professional Associations', 'Industry Forums', 'Networking Groups'],
            'certifications': ['Industry Certifications', 'Professional Development', 'Skill Assessments', 'Continuing Education'],
            'portfolios': ['LinkedIn', 'Personal Website', 'Professional Profiles', 'Work Samples']
        }

def get_open_source_resources_for_topic(topic):
    """Get curated open source learning resources for a specific topic"""
    resources = {
        'programming': {
            'courses': [
                {'name': 'freeCodeCamp', 'url': 'https://www.freecodecamp.org/'},
                {'name': 'Codecademy', 'url': 'https://www.codecademy.com/'},
                {'name': 'Khan Academy', 'url': 'https://www.khanacademy.org/'},
            ],
            'practice': [
                {'name': 'LeetCode', 'url': 'https://leetcode.com/'},
                {'name': 'HackerRank', 'url': 'https://www.hackerrank.com/'},
            ],
            'communities': [
                {'name': 'Stack Overflow', 'url': 'https://stackoverflow.com/'},
                {'name': 'Reddit r/programming', 'url': 'https://www.reddit.com/r/programming/'},
            ]
        },
        'data science': {
            'courses': [
                {'name': 'Coursera - Data Science Specialization', 'url': 'https://www.coursera.org/specializations/jhu-data-science'},
                {'name': 'Kaggle Learn', 'url': 'https://www.kaggle.com/learn'},
                {'name': 'edX - MIT Intro to CS', 'url': 'https://www.edx.org/course/introduction-computer-science-mitx-6-00-1x-10'},
            ],
            'practice': [
                {'name': 'Kaggle Competitions', 'url': 'https://www.kaggle.com/competitions'},
                {'name': 'Google Colab', 'url': 'https://colab.research.google.com/'},
            ],
            'communities': [
                {'name': 'Kaggle Community', 'url': 'https://www.kaggle.com/discussion'},
                {'name': 'Towards Data Science', 'url': 'https://towardsdatascience.com/'},
            ]
        },
        'web development': {
            'courses': [
                {'name': 'Mozilla Developer Network (MDN)', 'url': 'https://developer.mozilla.org/'},
                {'name': 'W3Schools', 'url': 'https://www.w3schools.com/'},
                {'name': 'React Official Docs', 'url': 'https://react.dev/'},
            ],
            'practice': [
                {'name': 'CodePen', 'url': 'https://codepen.io/'},
                {'name': 'JSFiddle', 'url': 'https://jsfiddle.net/'},
            ],
            'communities': [
                {'name': 'CSS-Tricks', 'url': 'https://css-tricks.com/'},
                {'name': 'Smashing Magazine', 'url': 'https://www.smashingmagazine.com/'},
            ]
        }
    }
   
    topic_lower = topic.lower()
    for keyword, res_set in resources.items():
        if keyword in topic_lower:
            return res_set
   
    return {
        'courses': [
            {'name': 'Coursera', 'url': 'https://www.coursera.org/'},
            {'name': 'edX', 'url': 'https://www.edx.org/'},
            {'name': 'Khan Academy', 'url': 'https://www.khanacademy.org/'},
        ],
        'practice': [
            {'name': 'GitHub', 'url': 'https://github.com/'},
            {'name': 'Stack Overflow', 'url': 'https://stackoverflow.com/'},
        ],
        'communities': [
            {'name': 'Reddit', 'url': 'https://www.reddit.com/'},
            {'name': 'Discord Learning Communities', 'url': 'https://discord.com/'},
        ]
    }
# --- UI Layout and Styling ---
st.set_page_config(
    page_title="Learning Path Platform",
    page_icon="🎓",
    layout="wide",
    menu_items=None  # Removes Streamlit menu
)

st.markdown("""
<style>
    /* Hide Streamlit header and menu */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display:none;}
    div[data-testid="stToolbar"] {display:none;}
    /* Animated gradient background */
    .stApp {
        background: linear-gradient(135deg, #0a1a40, #1e3a8a, #0a1a40);
        background-size: 400% 400%;
        animation: gradientShift 10s ease infinite;
    }

    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }


    /* Smooth Gradient Background Animation */
    body {
        background: linear-gradient(135deg, #0a1a40, #00112b, #0a1a40);
        background-size: 300% 300%;
        animation: gradientShift 12s ease infinite;
        color: #f8f9fa;
        font-family: 'Poppins', sans-serif;
    }

    @keyframes gradientShift {
        0% {background-position: 0% 50%;}
        50% {background-position: 100% 50%;}
        100% {background-position: 0% 50%;}
    }

    /* Main Header */
    .main-header {
        background: linear-gradient(135deg, rgba(30,58,138,0.9), rgba(59,130,246,0.8));
        padding: 30px;
        border-radius: 15px;
        color: #f8f9fa;
        text-align: center;
        margin-bottom: 40px;
        box-shadow: 0 8px 25px rgba(0,0,0,0.4);
        backdrop-filter: blur(10px);
        animation: fadeInDown 1s ease-out;
    }
    .main-header h1 {
        font-size: 2.8em;
        margin-bottom: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        background: linear-gradient(90deg, #60a5fa, #3b82f6, #2563eb);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .main-header p {
        font-size: 1.2em;
        opacity: 0.9;
        color: #e2e8f0;
    }

    @keyframes fadeInDown {
        from {opacity: 0; transform: translateY(-25px);}
        to {opacity: 1; transform: translateY(0);}
    }

    /* Login/Register Container */
    .login-container {
        max-width: 500px;
        margin: 50px auto;
        padding: 40px;
        background: rgba(17,24,39,0.8);
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        animation: fadeIn 0.8s ease-out;
        color: #f1f5f9;
        border: 1px solid rgba(255,255,255,0.1);
        backdrop-filter: blur(8px);
    }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(90deg, #2563eb 0%, #3b82f6 100%);
        color: white;
        border: none;
        padding: 12px 25px;
        border-radius: 30px;
        font-weight: bold;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .stButton>button:hover {
        transform: translateY(-3px) scale(1.03);
        box-shadow: 0 6px 25px rgba(37,99,235,0.5);
    }

    /* Inputs */
    .stTextInput>div>div>input,
    .stTextArea>div>textarea,
    .stSelectbox>div>div,
    .stFileUploader>div>div {
        background-color: rgba(31,41,55,0.9) !important;
        border: 1px solid #374151 !important;
        border-radius: 10px !important;
        padding: 10px 15px !important;
        color: #f8f9fa !important;
        transition: 0.3s ease;
    }
    .stTextInput>div>div>input:focus,
    .stTextArea>div>textarea:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 8px rgba(59,130,246,0.5) !important;
    }

    /* Dashboard Cards */
    .dashboard-card {
        background: rgba(30,41,59,0.9);
        padding: 25px;
        border-radius: 18px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.3);
        margin-bottom: 25px;
        transition: all 0.3s ease;
        color: #e2e8f0;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .dashboard-card:hover {
        box-shadow: 0 8px 30px rgba(59,130,246,0.4);
        transform: translateY(-5px);
    }
    .dashboard-card h3 {
        color: #60a5fa;
        margin-bottom: 15px;
        font-weight: 600;
    }

    /* Progress Bar */
    .stProgress > div > div > div > div {
        background-color: #3b82f6 !important;
    }

    /* Skill Tags */
    .skill-tag, .achievement-badge {
        display: inline-block;
        background-color: #1d4ed8;
        color: #e0e7ff;
        padding: 8px 18px;
        border-radius: 25px;
        margin: 5px;
        font-size: 0.9em;
        font-weight: 500;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }
    .achievement-badge {
        background: linear-gradient(45deg, #ffd700 0%, #ffed4e 100%);
        color: #1e293b;
        font-weight: bold;
    }

    /* Fade In Animation */
    @keyframes fadeIn {
        from {opacity: 0; transform: translateY(20px);}
        to {opacity: 1; transform: translateY(0);}
    }
</style>
""", unsafe_allow_html=True)


# --- Page Functions ---
def login_page():
    """Display login and registration page"""
    st.markdown("""
    <div class="main-header">
        <h1>🎓 BugBuster Learning Platform</h1>
        <p>Your Gateway to Personalized Learning</p>
    </div>
    """, unsafe_allow_html=True)
   
    col1, col2, col3 = st.columns([1, 2, 1])
   
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
       
        tab1, tab2 = st.tabs(["Login", "Register"])
       
        with tab1:
            st.markdown('<h3 style="text-align: center; margin-bottom: 30px; color: #667eea;">Welcome Back!</h3>', unsafe_allow_html=True)
           
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
           
            if st.button("Login", key="login_btn", use_container_width=True):
                if authenticate_user(username, password):
                    st.session_state.current_user = username
                    user_data = st.session_state.users_db.get(username, {})
                    if not user_data.get('profile', {}).get('onboarding_completed', False):
                        st.session_state.current_page = 'onboarding'
                    else:
                        st.session_state.current_page = 'dashboard'
                    st.rerun()
                else:
                    st.error("Invalid username or password")
       
        with tab2:
            st.markdown('<h3 style="text-align: center; margin-bottom: 30px; color: #764ba2;">Join MetaZord</h3>', unsafe_allow_html=True)
           
            reg_username = st.text_input("Username", key="reg_username")
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            reg_confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm_password")
           
            if st.button("Register", key="register_btn", use_container_width=True):
                if not reg_username or not reg_email or not reg_password or not reg_confirm_password:
                    st.error("All fields are required for registration.")
                elif reg_password != reg_confirm_password:
                    st.error("Passwords do not match")
                elif len(reg_password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    success, message = register_user(reg_username, reg_email, reg_password)
                    if success:
                        st.success(message)
                        st.session_state.current_user = reg_username
                        st.session_state.current_page = 'onboarding'
                        st.rerun()
                    else:
                        st.error(message)
       
        st.markdown('</div>', unsafe_allow_html=True)

def onboarding_page():
    """User onboarding and skills assessment"""
    user_data = st.session_state.users_db[st.session_state.current_user]
   
    st.markdown(f"""
    <div class="main-header">
        <h1>👋 Welcome, {st.session_state.current_user}!</h1>
        <p>Let's personalize your learning experience</p>
    </div>
    """, unsafe_allow_html=True)
   
    with st.container():
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.markdown("## 📝 Tell Us About Yourself")
       
        col1, col2 = st.columns(2)
       
        with col1:
            bio = st.text_area(
                "Brief Introduction",
                placeholder="Tell us about yourself, your background, and what you're passionate about...",
                value=user_data['profile']['bio']
            )
           
            experience_level = st.selectbox(
                "Experience Level",
                ["Beginner", "Intermediate", "Advanced", "Expert"],
                index=["Beginner", "Intermediate", "Advanced", "Expert"].index(user_data['profile']['experience_level'])
            )
       
        with col2:
            st.markdown("### 🛠 Current Skills")
            available_skills = [
                "Python", "JavaScript", "Java", "C++", "React", "Node.js", "SQL", "Machine Learning",
                "Data Science", "Web Development", "Mobile Development", "DevOps", "Cloud Computing",
                "Cybersecurity", "UI/UX Design", "Project Management", "Marketing", "Sales",
                "Finance", "Digital Marketing", "Content Writing", "Graphic Design", "Blockchain", "IoT"
            ]
           
            selected_skills = st.multiselect(
                "Select your current skills:",
                available_skills,
                default=user_data['profile']['skills']
            )
           
            st.markdown("### 🎯 Learning Goals")
            learning_goals = st.multiselect(
                "What do you want to learn?",
                [
                    "Career Advancement", "Skill Enhancement", "New Technology", "Certification",
                    "Personal Interest", "Startup/Entrepreneurship", "Academic Studies", "Problem Solving"
                ],
                default=user_data['profile']['learning_goals']
            )
       
        st.markdown("### 🌟 Areas of Interest")
        interests = st.multiselect(
            "Select areas that interest you:",
            [
                "Technology", "Business", "Arts & Design", "Science", "Healthcare",
                "Education", "Finance", "Marketing", "Engineering", "Psychology",
                "Literature", "History", "Music", "Sports", "Travel", "Environment"
            ],
            default=user_data['profile']['interests']
        )
       
        st.markdown("### ⏰ Learning Preferences")
        col1_pref, col2_pref, col3_pref = st.columns(3)
       
        with col1_pref:
            time_commitment = st.selectbox(
                "How much time can you dedicate per week?",
                ["1-5 hours", "6-10 hours", "11-20 hours", "20+ hours"],
                index=["1-5 hours", "6-10 hours", "11-20 hours", "20+ hours"].index(user_data['profile'].get('time_commitment', '1-5 hours'))
            )
       
        with col2_pref:
            learning_style = st.selectbox(
                "Preferred learning style",
                ["Visual", "Reading/Writing", "Hands-on", "Auditory", "Mixed"],
                index=["Visual", "Reading/Writing", "Hands-on", "Auditory", "Mixed"].index(user_data['profile'].get('learning_style', 'Visual'))
            )
       
        with col3_pref:
            difficulty_preference = st.selectbox(
                "Preferred difficulty",
                ["Beginner-friendly", "Challenging", "Mixed"],
                index=["Beginner-friendly", "Challenging", "Mixed"].index(user_data['profile'].get('difficulty_preference', 'Beginner-friendly'))
            )
       
        if st.button("💾 Save Profile & Continue", key="save_profile", use_container_width=True):
            user_data['profile'].update({
                'bio': bio,
                'experience_level': experience_level,
                'skills': selected_skills,
                'learning_goals': learning_goals,
                'interests': interests,
                'time_commitment': time_commitment,
                'learning_style': learning_style,
                'difficulty_preference': difficulty_preference,
                'onboarding_completed': True
            })
           
            if st.session_state.current_user not in st.session_state.learning_progress_data['skill_progress']:
                 st.session_state.learning_progress_data['skill_progress'][st.session_state.current_user] = {}

            st.success("Profile saved successfully! 🎉")
            st.session_state.current_page = 'dashboard'
            st.rerun()
       
        st.markdown('</div>', unsafe_allow_html=True)

def dashboard_page():
    """Main dashboard with navigation"""
    user_data = st.session_state.users_db[st.session_state.current_user]
   
    st.markdown(f"""
    <div class="main-header">
        <h1>🎓 Your Dashboard</h1>
        <p>Welcome back, {st.session_state.current_user}! Ready to continue your learning journey?</p>
    </div>
    """, unsafe_allow_html=True)
   
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "🎯 Learning Path", "📈 Progress", "📄 AI Resume", "👤 Profile"])
   
    with tab1:
        show_dashboard_overview(user_data)
    with tab2:
        show_learning_path_page(user_data)
    with tab3:
        show_progress_tracking(user_data)
    with tab4:
        show_ai_resume_page(user_data)
    with tab5:
        show_profile_page(user_data)

def show_dashboard_overview(user_data):
    """Show dashboard overview"""
    dashboard_data = progress_tracker.get_user_dashboard_data(st.session_state.current_user)
   
    if st.session_state.get('gemini_api_key'):
        st.success("🤖 AI Features: Enhanced with your API key")
    else:
        st.info("🤖 AI Features: Using default API key - Add your own in Profile for better performance")
   
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("Key Metrics")
    col1, col2, col3, col4 = st.columns(4)
   
    with col1:
        st.metric("Learning Streak", f"{dashboard_data.get('learning_streak', 0)} days", "🔥")
    with col2:
        st.metric("Completed Modules", f"{dashboard_data.get('completed_modules', 0)}", "✅")
    with col3:
        st.metric("Total Study Time", f"{dashboard_data.get('total_study_time', 0)} min", "⏰")
    with col4:
        st.metric("Achievements", f"{len(dashboard_data.get('achievements', []))}", "🏆")
   
    st.markdown('</div>', unsafe_allow_html=True)

    col_recent_activity, col_skills_goals = st.columns(2)

    with col_recent_activity:
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.subheader("💡 Learning Insights")
        insights = progress_tracker.get_learning_insights(st.session_state.current_user)
        if insights:
            for insight in insights:
                st.info(insight)
        else:
            st.info("No insights yet. Start your learning journey!")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_skills_goals:
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        st.subheader("🎯 Your Learning Goals")
        if user_data['profile']['learning_goals']:
            for goal in user_data['profile']['learning_goals']:
                st.markdown(f'<div class="skill-tag">{goal}</div>', unsafe_allow_html=True)
        else:
            st.info("No learning goals set yet. Visit the Profile page to set some!")
       
        st.subheader("🛠 Your Skills")
        if user_data['profile']['skills']:
            for skill in user_data['profile']['skills']:
                st.markdown(f'<div class="skill-tag">{skill}</div>', unsafe_allow_html=True)
        else:
            st.info("Add your skills in the Profile section.")
        st.markdown('</div>', unsafe_allow_html=True)

def show_learning_path_page(user_data):
    """Show learning path generation page"""
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("🎯 Create Your Learning Path")
   
    goal = st.text_input("🎯 What is your learning goal? (e.g., Become a Data Scientist)", key="dashboard_goal")
   
    if goal:
        use_prev = st.radio(
            "Would you like to leverage your existing skills for this path?",
            options=["Yes, use my previous skills", "No, start a fresh path"],
            index=0,
            key="dashboard_use_prev_skills"
        )

        skills = st.text_area("🛠 Current skills or experience (optional)", key="dashboard_skills",
                              value=", ".join(user_data['profile']['skills']))
        preferences = st.text_area("⚙ Learning preferences (e.g., visual, hands-on, short modules)", key="dashboard_preferences",
                                   value=f"Style: {user_data['profile']['learning_style']}, Time: {user_data['profile']['time_commitment']}, Difficulty: {user_data['profile']['difficulty_preference']}")
       
        uploaded_file = st.file_uploader("📄 Upload your resume or skill list (optional)", type=["txt", "pdf", "docx"], key="dashboard_resume")
       
        if st.button("🚀 Generate My Learning Path", key="dashboard_generate", use_container_width=True):
            resume_content = get_file_content(uploaded_file) if uploaded_file else ""
            use_prev_bool = (use_prev == "Yes, use my previous skills")
           
            with st.spinner("🤖 Generating your personalized learning path... This might take a moment."):
                result = generate_learning_path_ai(
                    user_profile=user_data['profile'],
                    goal=goal,
                    additional_skills=skills,
                    preferences=preferences,
                    resume_content=resume_content,
                    use_previous_skills=use_prev_bool
                )
           
            if result['success']:
                learning_path_content = result['learning_path']
                is_ai_generated = result.get('ai_generated', True)
                is_career_readiness = result.get('career_readiness', False)
               
                user_paths = st.session_state.users_db[st.session_state.current_user]['learning_paths']
                path_id = f"path_{len(user_paths)}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                path_data = {
                    'id': path_id,
                    'goal': goal,
                    'path': learning_path_content,
                    'created_at': datetime.now().isoformat(),
                    'status': 'Active',
                    'ai_generated': is_ai_generated,
                    'career_readiness': is_career_readiness
                }
                user_paths.append(path_data)
               
                progress_tracker.log_daily_activity(
                    st.session_state.current_user,
                    'study',
                    duration_minutes=60,
                    details=f"Generated new learning path for: {goal}"
                )
                progress_tracker.add_achievement(st.session_state.current_user, "First Learning Path Created", 'general')
               
                if is_ai_generated:
                    st.success("🤖 AI-powered learning path generated successfully! 🎉")
                else:
                    st.success("📚 Career readiness path generated successfully! 🎉")
                    st.info("💡 *Want AI-powered paths?* Add your Gemini API key in the settings for personalized learning recommendations!")
               
                # --- Generate and display learning path flowchart ---
                st.markdown("### 🛤 Learning Path Flowchart")
                try:
                    learning_flowchart_img = generate_learning_path_flowchart(user_data['profile'], goal, use_prev_bool)

                    if learning_flowchart_img:
                        # Display clearer and larger flowchart
                        st.image(
                            learning_flowchart_img,
                            width=1000,
                            caption="📊 AI Learning Path Flowchart",
                            output_format="auto"
                        )

                        # Download + Info section
                        col_download1, col_download2 = st.columns([1, 1])
                        with col_download1:
                            st.download_button(
                                label="📥 Download Learning Path Flowchart",
                                data=learning_flowchart_img,
                                file_name=f"learning_path_flowchart_{goal.replace(' ', '_').lower()}.png",
                                mime="image/png",
                                key="download_learning_flowchart"
                            )
                        with col_download2:
                            st.info("💡 Save this flowchart to track your learning journey!")
                    else:
                        st.warning("⚠️ Could not generate learning path flowchart")

                except Exception as e:
                    st.warning(f"❌ Could not generate flowchart: {e}")

                # Also show career readiness flowchart if applicable
                if is_career_readiness:
                    st.markdown("### 🎯 Career Readiness Flowchart")
                    try:
                        career_flowchart_img = generate_career_readiness_flowchart(user_data['profile'], goal, use_prev_bool)
                        if career_flowchart_img:
                            st.image(career_flowchart_img)
                           
                            col_download3, col_download4 = st.columns([1, 1])
                            with col_download3:
                                st.download_button(
                                    label="📥 Download Career Readiness Flowchart",
                                    data=career_flowchart_img,
                                    file_name=f"career_readiness_flowchart_{goal.replace(' ', '_').lower()}.png",
                                    mime="image/png",
                                    key="download_career_flowchart"
                                )
                            with col_download4:
                                st.info("💡 Save this flowchart to track your career readiness journey!")
                    except Exception as e:
                        st.warning(f"Could not generate career readiness flowchart: {e}")
               
                st.markdown("### 📝 Detailed Learning Path")
                st.markdown(learning_path_content)
               
                st.markdown("### 📚 Recommended Open Source Resources")
                resources = get_open_source_resources_for_topic(goal)
               
                col_courses, col_practice, col_communities = st.columns(3)
               
                with col_courses:
                    st.markdown("🎓 Top Courses**")
                    for r in resources['courses']:
                        st.markdown(f"• [{r['name']}]({r['url']})")
               
                with col_practice:
                    st.markdown("💻 Practice Platforms**")
                    for r in resources['practice']:
                        st.markdown(f"• [{r['name']}]({r['url']})")
               
                with col_communities:
                    st.markdown("🤝 Communities**")
                    for r in resources['communities']:
                        st.markdown(f"• [{r['name']}]({r['url']})")
               
                # Download options for learning path
                st.markdown("### 📥 Download Options")
                col_download_text, col_download_learning_flow, col_download_career_flow = st.columns(3)
               
                with col_download_text:
                    # Convert learning path to downloadable format
                    path_text = learning_path_content
                    st.download_button(
                        label="📄 Download Learning Path (TXT)",
                        data=path_text,
                        file_name=f"learning_path_{goal.replace(' ', '_').lower()}.txt",
                        mime="text/plain",
                        key="download_path"
                    )
               
                with col_download_learning_flow:
                    if 'learning_flowchart_img' in locals() and learning_flowchart_img:
                        st.download_button(
                            label="🛤 Download Learning Flowchart (PNG)",
                            data=learning_flowchart_img,
                            file_name=f"learning_path_flowchart_{goal.replace(' ', '_').lower()}.png",
                            mime="image/png",
                            key="download_learning_flowchart_2"
                        )
                    else:
                        st.info("💡 Learning path flowchart available above")
               
                with col_download_career_flow:
                    if is_career_readiness and 'career_flowchart_img' in locals() and career_flowchart_img:
                        st.download_button(
                            label="🎯 Download Career Flowchart (PNG)",
                            data=career_flowchart_img,
                            file_name=f"career_readiness_flowchart_{goal.replace(' ', '_').lower()}.png",
                            mime="image/png",
                            key="download_career_flowchart_2"
                        )
                    else:
                        st.info("💡 Career readiness flowchart available for career-focused paths")
       
        st.markdown('</div>', unsafe_allow_html=True)

def show_progress_tracking(user_data):
    """Show progress tracking page"""
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📈 Your Learning Progress")
   
    dashboard_data = progress_tracker.get_user_dashboard_data(st.session_state.current_user)
   
    # Small widget showing number of days
    col_days, col_streak, col_time = st.columns(3)
   
    with col_days:
        total_days = len(set([a['date'] for a in dashboard_data['activities'] if a.get('duration_minutes', 0) > 0]))
        st.metric("📅 Active Days", f"{total_days} days", help="Total days with learning activity")
   
    with col_streak:
        streak = dashboard_data.get('learning_streak', 0)
        st.metric("🔥 Current Streak", f"{streak} days", help="Consecutive days of learning")
   
    with col_time:
        total_time = dashboard_data.get('total_study_time', 0)
        hours = total_time // 60
        minutes = total_time % 60
        st.metric("⏰ Total Time", f"{hours}h {minutes}m", help="Total study time logged")
   
    # Progress charts
    charts = progress_tracker.create_progress_charts(st.session_state.current_user)
   
    if charts:
        col1, col2 = st.columns(2)
       
        with col1:
            if 'daily_activity' in charts:
                st.plotly_chart(charts['daily_activity'], use_container_width=True)
       
        with col2:
            if 'skills_progress' in charts:
                st.plotly_chart(charts['skills_progress'], use_container_width=True)
   
    # Manual progress update
    st.markdown("### 📝 Update Your Progress")
    col1, col2 = st.columns(2)
   
    with col1:
        activity_type = st.selectbox("Activity Type", ["study", "course", "project", "practice", "other"])
        duration = st.number_input("Duration (minutes)", min_value=0, max_value=480, value=60)
   
    with col2:
        skill_name = st.text_input("Skill/Subject", placeholder="e.g., Python, Data Science")
        details = st.text_area("Details", placeholder="What did you work on?")
   
    if st.button("📊 Log Activity", key="log_activity"):
        if skill_name:
            progress_tracker.log_daily_activity(
                st.session_state.current_user,
                activity_type,
                duration,
                details
            )
           
            # Update skill progress
            if skill_name:
                current_progress = dashboard_data['skills'].get(skill_name, {}).get('progress', 0)
                new_progress = min(100, current_progress + 5)  # Add 5% for each activity
                progress_tracker.update_skill_progress(
                    st.session_state.current_user,
                    skill_name,
                    new_progress,
                    experience_points=duration
                )
           
            st.success("✅ Activity logged successfully!")
            st.rerun()
   
    st.markdown('</div>', unsafe_allow_html=True)

def show_ai_resume_page(user_data):
    """Show AI resume generation page"""
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("📄 AI Resume Builder")
   
    # Resume generation form
    col1, col2 = st.columns(2)
   
    with col1:
        st.markdown("### 📝 Resume Information")
       
        # Get user's learning paths for resume content
        learning_paths = user_data.get('learning_paths', [])
       
        # Auto-fill career goal from learning paths if available
        default_goal = ""
        if learning_paths and len(learning_paths) > 0:
            latest_path = learning_paths[-1]
            if isinstance(latest_path, dict):
                default_goal = latest_path.get('goal', '')
       
        goal = st.text_input("Career Goal", value=default_goal, placeholder="e.g., Software Developer", key="resume_goal")
       
        # Auto-fill additional skills from user profile
        profile_skills_text = ", ".join(user_data['profile'].get('skills', []))
        additional_skills = st.text_area(
            "Additional Skills/Experience",
            value=profile_skills_text,
            placeholder="Add any additional skills or experience not in your profile...",
            key="resume_additional_skills"
        )
       
        # Resume format selection
        resume_format = st.selectbox(
            "Resume Template Style",
            ["Creative Colorful", "Modern Minimal", "Professional Elegant", "Tech Innovative"],
            key="resume_format"
        )
   
    with col2:
        st.markdown("### 🎯 Resume Preview")
       
        if learning_paths and isinstance(learning_paths, list) and len(learning_paths) > 0:
            st.info(f"📚 Found {len(learning_paths)} learning path(s) to include in resume")
            for i, path in enumerate(learning_paths[-3:]):  # Show last 3 paths
                if isinstance(path, dict):
                    st.markdown(f"• {path.get('goal', 'Learning Path')}")
                else:
                    st.markdown(f"• Learning Path {i+1}")
        else:
            st.warning("No learning paths found. Create a learning path first for better resume content.")
   
    # Generate resume button
    if st.button("🤖 Generate AI Resume", key="generate_resume", use_container_width=True):
        if not goal:
            st.error("Please enter a career goal for your resume.")
        else:
            with st.spinner("🤖 Generating your AI-powered resume..."):
                resume_content = generate_ai_resume(
                    user_profile=user_data['profile'],
                    learning_paths=learning_paths,
                    goal=goal
                )
           
            if resume_content and not resume_content.startswith("Error"):
                st.success("✅ Resume generated successfully!")
               
                # Display resume
                st.markdown("### 📄 Your Generated Resume")
                st.markdown(resume_content)
               
                # Download options
                st.markdown("### 📥 Download Your Resume")
                col_download_txt, col_download_pdf = st.columns(2)
               
                with col_download_txt:
                    st.download_button(
                        label="📄 Download as TXT",
                        data=resume_content,
                        file_name=f"resume_{goal.replace(' ', '_').lower()}.txt",
                        mime="text/plain",
                        key="download_resume_txt"
                    )
               
                with col_download_pdf:
                    # For PDF, we'll create a styled HTML version that can be printed to PDF
                    user_email = user_data.get('email', 'email@example.com')
                    user_time_commitment = user_data['profile'].get('time_commitment', 'Flexible')
                    user_experience_level = user_data['profile'].get('experience_level', 'Professional')
                   
                    html_resume = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Resume - {goal}</title>
                        <style>
                            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
                           
                            * {{
                                margin: 0;
                                padding: 0;
                                box-sizing: border-box;
                            }}
                           
                            body {{
                                font-family: 'Inter', sans-serif;
                                line-height: 1.6;
                                color: #333;
                                background: #f8f9fa;
                            }}
                           
                            .resume-container {{
                                max-width: 1200px;
                                margin: 20px auto;
                                background: white;
                                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                                border-radius: 10px;
                                overflow: hidden;
                            }}
                           
                            .resume-header {{
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                color: white;
                                padding: 40px;
                                text-align: center;
                                position: relative;
                                overflow: hidden;
                            }}
                           
                            .resume-header::before {{
                                content: '';
                                position: absolute;
                                top: -50%;
                                left: -50%;
                                width: 200%;
                                height: 200%;
                                background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
                                animation: float 6s ease-in-out infinite;
                            }}
                           
                            .resume-header::after {{
                                content: '';
                                position: absolute;
                                bottom: 0;
                                left: 0;
                                right: 0;
                                height: 20px;
                                background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 120" preserveAspectRatio="none"><path d="M0,0V46.29c47.79,22.2,103.59,32.17,158,28,70.36-5.37,136.33-33.31,206.8-37.5C438.64,32.43,512.34,53.67,583,72.05c69.27,18,138.3,24.88,209.4,13.08,36.15-6,69.85-17.84,104.45-29.34C989.49,25,1113-14.29,1200,52.47V0Z" opacity=".25" fill="white"></path></svg>') no-repeat center bottom;
                                background-size: cover;
                            }}
                           
                            @keyframes float {{
                                0%, 100% {{ transform: translateY(0px) rotate(0deg); }}
                                50% {{ transform: translateY(-20px) rotate(180deg); }}
                            }}
                           
                            .name {{
                                font-size: 2.8em;
                                font-weight: 700;
                                margin-bottom: 10px;
                                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                                position: relative;
                                z-index: 2;
                            }}
                           
                            .title {{
                                font-size: 1.4em;
                                opacity: 0.9;
                                font-weight: 300;
                                position: relative;
                                z-index: 2;
                            }}
                           
                            .resume-content {{
                                padding: 40px;
                                background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
                            }}
                           
                            .section {{
                                margin-bottom: 30px;
                                background: white;
                                padding: 25px;
                                border-radius: 15px;
                                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                                border-left: 5px solid #667eea;
                                transition: transform 0.3s ease, box-shadow 0.3s ease;
                            }}
                           
                            .section:hover {{
                                transform: translateY(-5px);
                                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
                            }}
                           
                            .section-title {{
                                font-size: 1.5em;
                                font-weight: 700;
                                color: #667eea;
                                margin-bottom: 20px;
                                padding-bottom: 10px;
                                border-bottom: 3px solid #e9ecef;
                                position: relative;
                                text-transform: uppercase;
                                letter-spacing: 1px;
                            }}
                           
                            .section-title::after {{
                                content: '';
                                position: absolute;
                                bottom: -3px;
                                left: 0;
                                width: 60px;
                                height: 3px;
                                background: linear-gradient(90deg, #667eea, #764ba2);
                                border-radius: 2px;
                            }}
                           
                            .bullet-points {{
                                list-style: none;
                                padding: 0;
                            }}
                           
                            .bullet-points li {{
                                position: relative;
                                padding-left: 25px;
                                margin-bottom: 12px;
                                line-height: 1.6;
                                color: #555;
                            }}
                           
                            .bullet-points li::before {{
                                content: '▶';
                                position: absolute;
                                left: 0;
                                color: #667eea;
                                font-weight: bold;
                                font-size: 0.8em;
                            }}
                           
                            .skills-grid {{
                                display: grid;
                                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                                gap: 20px;
                                margin-top: 20px;
                            }}
                           
                            .skill-category {{
                                background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
                                padding: 20px;
                                border-radius: 12px;
                                border-left: 5px solid #667eea;
                                box-shadow: 0 3px 10px rgba(0,0,0,0.1);
                                transition: transform 0.3s ease;
                            }}
                           
                            .skill-category:hover {{
                                transform: translateX(5px);
                            }}
                           
                            .skill-category h4 {{
                                color: #667eea;
                                margin-bottom: 12px;
                                font-size: 1.1em;
                                font-weight: 600;
                                text-transform: uppercase;
                                letter-spacing: 0.5px;
                            }}
                           
                            .skill-tags {{
                                display: flex;
                                flex-wrap: wrap;
                                gap: 8px;
                            }}
                           
                            .skill-tag {{
                                background: linear-gradient(135deg, #667eea, #764ba2);
                                color: white;
                                padding: 6px 12px;
                                border-radius: 20px;
                                font-size: 0.85em;
                                font-weight: 500;
                                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                            }}
                           
                            .experience-item, .education-item, .project-item {{
                                margin-bottom: 25px;
                                padding: 25px;
                                background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
                                border-radius: 12px;
                                border-left: 5px solid #667eea;
                                box-shadow: 0 3px 10px rgba(0,0,0,0.08);
                                transition: all 0.3s ease;
                            }}
                           
                            .experience-item:hover, .education-item:hover, .project-item:hover {{
                                transform: translateX(5px);
                                box-shadow: 0 8px 20px rgba(0,0,0,0.15);
                            }}
                           
                            .job-title {{
                                font-weight: 700;
                                color: #333;
                                font-size: 1.2em;
                                margin-bottom: 5px;
                            }}
                           
                            .company {{
                                color: #667eea;
                                font-weight: 600;
                                font-size: 1.1em;
                                margin-bottom: 5px;
                            }}
                           
                            .date {{
                                color: #6c757d;
                                font-size: 0.9em;
                                font-style: italic;
                                background: #e9ecef;
                                padding: 4px 8px;
                                border-radius: 15px;
                                display: inline-block;
                            }}
                           
                            .contact-info {{
                                display: flex;
                                justify-content: center;
                                gap: 40px;
                                margin-top: 25px;
                                flex-wrap: wrap;
                                position: relative;
                                z-index: 2;
                            }}
                           
                            .contact-item {{
                                display: flex;
                                align-items: center;
                                gap: 10px;
                                color: white;
                                opacity: 0.9;
                                background: rgba(255,255,255,0.1);
                                padding: 10px 15px;
                                border-radius: 25px;
                                backdrop-filter: blur(10px);
                                transition: all 0.3s ease;
                            }}
                           
                            .contact-item:hover {{
                                background: rgba(255,255,255,0.2);
                                transform: translateY(-2px);
                            }}
                           
                            .contact-item i {{
                                font-size: 1.2em;
                            }}
                           
                            @media print {{
                                body {{ background: white; }}
                                .resume-container {{ box-shadow: none; margin: 0; }}
                            }}
                           
                            @media (max-width: 768px) {{
                                .resume-header {{ padding: 30px 20px; }}
                                .resume-content {{ padding: 30px 20px; }}
                                .name {{ font-size: 2em; }}
                                .contact-info {{ flex-direction: column; gap: 15px; }}
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="resume-container">
                            <div class="resume-header">
                                <h1 class="name">{st.session_state.current_user}</h1>
                                <p class="title">{goal}</p>
                                <div class="contact-info">
                                    <div class="contact-item">
                                        <i>📧</i>
                                        <span>{user_email}</span>
                                    </div>
                                    <div class="contact-item">
                                        <i>🎯</i>
                                        <span>{user_experience_level} Professional</span>
                                    </div>
                                    <div class="contact-item">
                                        <i>⏰</i>
                                        <span>{user_time_commitment}</span>
                                    </div>
                                </div>
                            </div>
                           
                            <div class="resume-content">
                                {resume_content.replace('\n', '<br>')}
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                   
                    st.download_button(
                        label="📄 Download as HTML (Print to PDF)",
                        data=html_resume,
                        file_name=f"resume_{goal.replace(' ', '_').lower()}.html",
                        mime="text/html",
                        key="download_resume_html"
                    )
               
                # Log activity
                progress_tracker.log_daily_activity(
                    st.session_state.current_user,
                    'resume',
                    duration_minutes=30,
                    details=f"Generated resume for: {goal}"
                )
               
            else:
                st.error(f"❌ {resume_content}")
   
    st.markdown('</div>', unsafe_allow_html=True)

def show_profile_page(user_data):
    """Show user profile page"""
    st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
    st.subheader("👤 Your Profile")
   
    col1, col2 = st.columns(2)
   
    with col1:
        st.markdown("### 📝 Profile Information")
        st.markdown(f"**Username:** {st.session_state.current_user}")
        st.markdown(f"**Email:** {user_data.get('email', 'Not provided')}")
        st.markdown(f"**Experience Level:** {user_data['profile']['experience_level']}")
        st.markdown(f"**Time Commitment:** {user_data['profile']['time_commitment']}")
        st.markdown(f"**Learning Style:** {user_data['profile']['learning_style']}")
       
        if user_data['profile']['bio']:
            st.markdown("### 📖 Bio")
            st.markdown(user_data['profile']['bio'])
   
    with col2:
        st.markdown("### 🛠 Skills")
        if user_data['profile']['skills']:
            for skill in user_data['profile']['skills']:
                st.markdown(f'<div class="skill-tag">{skill}</div>', unsafe_allow_html=True)
        else:
            st.info("No skills added yet")
       
        st.markdown("### 🎯 Learning Goals")
        if user_data['profile']['learning_goals']:
            for goal in user_data['profile']['learning_goals']:
                st.markdown(f'<div class="skill-tag">{goal}</div>', unsafe_allow_html=True)
        else:
            st.info("No learning goals set yet")
   
    # API Key Management
    st.markdown("### 🤖 AI Settings")
    st.markdown("Add your Gemini API key for enhanced AI features:")
   
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="Enter your Gemini API key...",
        value=st.session_state.get('gemini_api_key', ''),
        key="api_key_input"
    )
   
    if st.button("💾 Save API Key", key="save_api_key"):
        if api_key:
            st.session_state.gemini_api_key = api_key
            st.success("✅ API key saved successfully!")
            st.rerun()
        else:
            st.error("Please enter a valid API key")
   
    # Edit profile button
    if st.button("✏️ Edit Profile", key="edit_profile"):
        st.session_state.current_page = 'onboarding'
        st.rerun()
   
    st.markdown('</div>', unsafe_allow_html=True)

# --- AI Assistant Chat Functionality ---
def show_ai_assistant_chat():
    """Show AI assistant chat interface"""
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
   
    # Chat interface
    st.markdown("### 🤖 AI Career Assistant")
   
    # Display chat messages
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
   
    # Chat input
    if prompt := st.chat_input("Ask me about your career path, skills, or learning goals..."):
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
       
        # Generate AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                if model:
                    try:
                        user_profile = st.session_state.users_db[st.session_state.current_user]['profile']
                        context = f"""
                        User Profile:
                        - Skills: {', '.join(user_profile.get('skills', []))}
                        - Experience Level: {user_profile.get('experience_level', 'Beginner')}
                        - Learning Goals: {', '.join(user_profile.get('learning_goals', []))}
                        - Time Commitment: {user_profile.get('time_commitment', '1-5 hours')}
                       
                        User Question: {prompt}
                       
                        Please provide helpful, personalized advice about their career development, learning path, or skill development. Be encouraging and specific to their profile.
                        """
                       
                        response = model.generate_content(context)
                        ai_response = response.text if response.text else "I'm sorry, I couldn't generate a response. Please try again."
                    except Exception as e:
                        ai_response = f"I apologize, but I encountered an error: {str(e)}. Please try again or check your API key."
                else:
                    ai_response = "I'd be happy to help! However, I need a Gemini API key to provide personalized AI assistance. Please add your API key in the Profile section for enhanced features."
       
        # Add AI response
        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
       
        # Rerun to show new messages
        st.rerun()

# --- Main Application Logic ---
def main():
    """Main application function"""
   
    # AI Assistant Icon in top left
    col1, col2, col3 = st.columns([1, 8, 1])
   
    with col1:
        if st.button("🤖", key="ai_assistant_btn", help="Open AI Assistant Chat"):
            if 'show_chat' not in st.session_state:
                st.session_state.show_chat = False
            st.session_state.show_chat = not st.session_state.show_chat
   
    with col2:
        pass  # Main content area
   
    with col3:
        if st.button("🚪", key="logout_btn", help="Logout"):
            st.session_state.current_user = None
            st.session_state.current_page = 'login'
            st.rerun()
   
    # Show AI Assistant Chat if toggled
    if st.session_state.get('show_chat', False):
        st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
        show_ai_assistant_chat()
        st.markdown('</div>', unsafe_allow_html=True)
   
    # Main page routing
    if st.session_state.current_page == 'login':
        login_page()
    elif st.session_state.current_page == 'onboarding':
        onboarding_page()
    elif st.session_state.current_page == 'dashboard':
        dashboard_page()
    else:
        login_page()

if __name__ == "__main__":
    main()

