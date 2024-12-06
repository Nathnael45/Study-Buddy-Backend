import json
from os import getenv, path
from db import db, Course, User
from flask import Flask, request, session
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from schedule_data import process_calendar_file, compress_availability, decompress_availability
from icalendar import Calendar
from dotenv import load_dotenv
from schedule_data import constructor_availability, preference_comparison
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from random import sample

load_dotenv()



# define db filename
db_filename = "data.db"
app = Flask(__name__)
print(getenv("FLASK_SECRET_KEY"))
app.secret_key = getenv("FLASK_SECRET_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True

# initialize app
db.init_app(app)
with app.app_context():
    db.create_all()

# generalized response formats
def success_response(data, code=200):
    return json.dumps(data), code
def failure_response(message, code=404):
    return json.dumps({"error": message}), code


#### NON-API ROUTES ------------------------------------------------------
def clear_users_courses(user_id):
    """Remove the currently logged-in user from all their courses"""
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
   
    if user_id is None:
        return failure_response("User not found", 404)
    
    # Clear all courses for this user
    user_id.student_courses = []
    db.session.commit()
    
    return success_response("User is no longer enrolled in any courses")
def get_common_preferences(user_id, buddy_id):
    """
    Returns a dictionary of preferences that two users have in common
    
    Args:
        user_id: ID of first user
        buddy_id: ID of second user
        
    Returns:
        dict: Dictionary containing matching preferences
    """
    user = User.query.get(user_id)
    buddy = User.query.get(buddy_id)
    
    if not user or not buddy:
        return {}
        
    common_prefs = {
        "locations": [],
        "times": [],
        "objectives": []
    }
    
    # Check location preferences
    if user.location_north and buddy.location_north:
        common_prefs["locations"].append("north")
    if user.location_south and buddy.location_south:
        common_prefs["locations"].append("south")
    if user.location_central and buddy.location_central:
        common_prefs["locations"].append("central")
    if user.location_west and buddy.location_west:
        common_prefs["locations"].append("west")
    
    # Check time preferences
    if user.time_morning and buddy.time_morning:
        common_prefs["times"].append("morning")
    if user.time_afternoon and buddy.time_afternoon:
        common_prefs["times"].append("afternoon")
    if user.time_evening and buddy.time_evening:
        common_prefs["times"].append("evening")
    
    # Check objective preferences
    if user.objective_study and buddy.objective_study:
        common_prefs["objectives"].append("study")
    if user.objective_homework and buddy.objective_homework:
        common_prefs["objectives"].append("homework")
    
    return common_prefs
   




@app.route("/api/create/", methods=["POST"])
def create_user():
    """Create a new user"""
    body = json.loads(request.data)
    
    try:
        name, netid, password, confirm_password = body["name"], body["netid"], body["password"], body["confirm_password"]
    except:
        return failure_response("Missing Entry Fields", 400)
    
    if password != confirm_password:
        return failure_response("Passwords do not match", 400)
    
    existing_user = User.query.filter_by(netid=netid).first()
    if existing_user is not None:
        return failure_response("User already exists", 400)
    
    # Hash the password before storing
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    
    # Create new user with keyword arguments
    new_user = User(
        name=name,
        netid=netid,
        password=hashed_password
    )
    
    db.session.add(new_user)
    db.session.commit()

    return success_response(new_user.serialize(), 201)

@app.route("/api/login/", methods=["POST"])
def login_user():
    """Login a user"""
    body = json.loads(request.data)    

    try:
        netid, request_password = body["netid"], body["password"]
    except:
        return failure_response("Missing Entry Fields", 400)
    
    user = User.query.filter_by(netid=netid).first()
    
    if user is None:
        return failure_response("User Not Found: Invalid NetId", 404)


    # Use check_password_hash to verify the password
    elif not check_password_hash(user.password, request_password):
        return failure_response("Password incorrect", 400)
    
    session["user_id"] = user.id
    return success_response(user.serialize())

@app.route("/api/upload/", methods=["POST"])
def upload_file():
    """Upload a file for the logged-in user"""
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    # Check if a file was uploaded
    if "file" not in request.files:
        return json.dumps({"error": "No file part in the request"}), 400
    
    cal_file = request.files["file"]
    
    # Check if the file has a valid name
    if cal_file.filename == "":
        return json.dumps({"error": "No file selected"}), 400
    
    temp_file_path =  path.join("/tmp", cal_file.filename)
    cal_file.save(temp_file_path)
    
    # Open the .ics file in binary mode
    with open(temp_file_path, 'rb') as f:
        cal = Calendar.from_ical(f.read())
        
    user_course_set = set()
    user_unavailability_blocks = []

    # Iterate through calendar components
    for component in cal.walk():
        if component.name == "VEVENT":
            
            period = component.get('summary')
            dtstart = component.get('dtstart').dt
            dtend = component.get('dtend').dt
            
            user_course_set.add(period.split(",")[0])
            user_unavailability_blocks.append((dtstart, dtend))

    # Get current user
    user = User.query.filter_by(id=session["user_id"]).first()
    clear_users_courses(user)

    for course_name in user_course_set:
        # Find or create the course
        # Note: Course requires both code and name
        course = Course.query.filter_by(name=course_name).first()
        if course is None:
            course = Course(
                code=course_name,  
                name=course_name
            )
            db.session.add(course)
        
        
        
        # Add user as student if not already in course
        if user not in course.students:
            course.students.append(user)
            # The reciprocal relationship will be automatically handled
            # because we defined back_populates in the models
    
    user.availability = constructor_availability(user_unavailability_blocks)
    
    db.session.commit()
    
    return success_response({"message": "Calendar processed successfully"})

@app.route("/api/user/preferences/", methods=["POST"])
def update_preferences():
    """Update user preferences for locations, times, and objectives
    
    Request body can contain any combination of these boolean fields:
    - location_north
    - location_south
    - location_central
    - location_west
    - time_morning
    - time_afternoon
    - time_evening
    - objective_study
    - objective_homework
    """
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    body = json.loads(request.data)
    user = User.query.filter_by(id=session["user_id"]).first()
    
    if user is None:
        return failure_response("User not found", 404)
    
    # List of valid preference fields
    valid_preferences = [
        'location_north', 'location_south', 'location_central', 'location_west',
        'time_morning', 'time_afternoon', 'time_evening',
        'objective_study', 'objective_homework'
    ]
    
    # Update only the preferences that were provided in the request
    for pref in valid_preferences:
        if pref in body:
            if not isinstance(body[pref], bool):
                return failure_response(f"Preference {pref} must be a boolean value", 400)
            setattr(user, pref, body[pref])
    
    db.session.commit()
    
    return success_response({
        "message": "Preferences updated successfully",
        "preferences": {
            "locations": {
                "north": user.location_north,
                "south": user.location_south,
                "central": user.location_central,
                "west": user.location_west
            },
            "times": {
                "morning": user.time_morning,
                "afternoon": user.time_afternoon,
                "evening": user.time_evening
            },
            "objectives": {
                "study": user.objective_study,
                "homework": user.objective_homework
            }
        }
    })

@app.route("/api/users/<string:netid>/")
def get_user(netid):
    """Get a specific user"""
    print(netid)
    user = User.query.filter_by(netid=netid).first()
    if user is None:
        return failure_response("User not found")
    return success_response(user.serialize())

@app.route("/api/logout/", methods=["POST"])
def logout():
    """Logout the current user"""
    session.pop("user_id", None)
    return success_response({"message": "Successfully logged out"})

@app.route("/api/send-email/", methods=["POST"])
def send_match_email():
    """Send emails to two matched users"""
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    body = json.loads(request.data)
    
    try:
        r_netid, s_netid = session["user_id"], body["sender_netid"]
    except:
        return failure_response("Missing netid fields", 400)
    
    # Get user objects
    user1 = User.query.filter_by(netid=r_netid).first()
    user2 = User.query.filter_by(netid=s_netid).first()
    
    common_prefs = get_common_preferences(user1.id, user2.id)
    
    pref_text = "\n".join([
        f"Locations: {', '.join(common_prefs['locations']) if common_prefs['locations'] else 'None'}",
        f"Times: {', '.join(common_prefs['times']) if common_prefs['times'] else 'None'}",
        f"Objectives: {', '.join(common_prefs['objectives']) if common_prefs['objectives'] else 'None'}"
    ])
    
    if user1 is None or user2 is None:
        return failure_response("One or both users not found", 404)
    
    # Email configuration
    sender_email =  getenv("EMAIL_ADDRESS")
    sender_password =  getenv("EMAIL_PASSWORD")
    
    # Create emails for both users
    for recipient in [user1, user2]:
        match = user1 if recipient == user2 else user2
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = f"{recipient.netid}@cornell.edu"
        msg['Subject'] = "You've been matched for studying!"
        
        body = f"""
        Hi {recipient.name},
        
        You've been matched with {match.name} ({match.netid}@cornell.edu) for studying!
        
        You both have the following in common:
        {pref_text}
        
        You can reach out to them directly to coordinate your study session.
        
        Best regards,
        Study Buddy Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            # Create SMTP session
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            
            # Send email
            server.send_message(msg)
            server.quit()
        except Exception as e:
            return failure_response(f"Failed to send email: {str(e)}", 500)
    
    return success_response({"message": "Emails sent successfully"})

@app.route("/api/search/")
def search_results():
    """Get search results for a user, sorted by match score"""
    SEARCH_LIMIT = 10
    
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    user = User.query.get(session["user_id"])
    if user is None:
        return failure_response("User not found", 404)
    
    # Get all coursemates
    coursemates = set()  # Using set to avoid duplicates
    coursemate_courses = {}  # Dictionary to track shared courses
    
    for course in user.student_courses:
        for student in course.students:
            if student.id != user.id:  # Exclude the current user
                coursemates.add(student)
                # Track shared courses for each coursemate
                if student.id not in coursemate_courses:
                    coursemate_courses[student.id] = set()
                coursemate_courses[student.id].add(course)
    
    if len(coursemates) == 0:
        return failure_response("No coursemates found", 404)
    
    # Calculate scores and build response data
    matches = []
    for coursemate in coursemates:
        score = preference_comparison(user, coursemate)
        
        common_prefs = get_common_preferences(user.id, coursemate.id)

        matches.append({
            "name": coursemate.name,
            "netid": coursemate.netid,
            "match_score": score,
            "common_courses": [course.code for course in coursemate_courses[coursemate.id]],
            "common_preferences": common_prefs
        })
    
    # Sort by match score (highest first)
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Limit number of results
    if len(matches) > SEARCH_LIMIT:
        matches = matches[:SEARCH_LIMIT]
    
    print(matches)
    
    return success_response({
        "matches": matches
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)













