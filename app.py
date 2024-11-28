import json, os, boto3
from db import db, Course, User
from flask import Flask, request, session
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from schedule_data import process_calendar_file, compress_availability, decompress_availability

# define db filename
db_filename = "data.db"
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

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

# -- FILE ROUTES ------------------------------------------------------

S3_BUCKET = "schedule-data-bucket"

def upload_file_to_s3(file_name):
    """Upload a file to an S3 bucket"""

    s3 = boto3.client("s3")
    try:
        s3.upload_file(file_name, S3_BUCKET, "user" + session["user_id"] + "schedule")
    except FileNotFoundError:
        return False
    return True


@app.route("/")
@app.route("/api/create/", methods=["POST"])
def create_user():
    """Create a new user"""
    body = json.loads(request.data)
    
    # Check if required fields exist
    if not body.get("name") or not body.get("netid") or not body.get("password") or not body.get("confirm_password"):
        return failure_response("Missing required fields", 400)
    
    name = body.get("name")
    netid = body.get("netid")
    password = body.get("password")
    confirm_password = body.get("confirm_password")
    
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
        netid, password = body.get("netid"), body.get("password")
    except:
        return failure_response("Missing fields", 400)
    
    user = User.query.filter_by(netid=netid).first()
    if user is None:
        return failure_response("Netid not found", 400)
    # Use check_password_hash to verify the password
    elif not check_password_hash(user.password, password):
        return failure_response("Incorrect password", 400)
    
    session["user_id"] = user.id
    return success_response("Successfully logged in", 200)


@app.route("/api/upload/", methods=["POST"])
def upload_file():
    """Upload a file for the logged-in user"""
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    # Check if a file was uploaded
    if "file" not in request.files:
        return json.dumps({"error": "No file part in the request"}), 400
    
    file = request.files["file"]
    
    # Check if the file has a valid name
    if file.filename == "":
        return json.dumps({"error": "No file selected"}), 400
    
    # Save the file temporarily to upload to S3
    temp_file_path = os.path.join("/tmp", file.filename)
    file.save(temp_file_path)
    
    # Define the object name in S3
    object_name = "user" + session["user_id"] + "/" + file.filename
    
    # Upload to S3
    success = upload_file_to_s3(temp_file_path)
    
    # Clean up the temporary file
    os.remove(temp_file_path)
    
    if not success:
        return failure_response("File upload failed"), 500
    else:
        availability_string = compress_availability(process_calendar_file(file))
        user = User(availability=availability_string)
        db.session.add(user)
        db.session.commit()
        return success_response({"message": "File uploaded successfully", "s3_key": object_name, "compressed_string": compressed_string}, 200)


@app.route("/api/results/", methods=["GET"])
def get_results():
    """Get the results for the logged-in user"""
    if "user_id" not in session:
        return failure_response("Not logged in", 401)
    
    user = User.query.filter_by(id=session["user_id"]).first()
    if user is None:
        return failure_response("User not found")
    return success_response(user.serialize())

# -- USER ROUTES ------------------------------------------------------

@app.route("/api/user/preferences/", methods=["POST"])
def update_preferences():
    """Update user preferences"""
    body = json.loads(request.data)


###########
@app.route("/api/users/<int:user_id>/")
def get_user(user_id):
    """Get a specific user"""
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found")
    return success_response(user.serialize())

@app.route("/api/courses/<int:course_id>/add/", methods=["POST"])
def add_user_to_course(course_id):
    """Add a student to a course"""
    course = Course.query.filter_by(id=course_id).first()
    if course is None:
        return failure_response("Course not found")
    
    body = json.loads(request.data)
    user = User.query.filter_by(id=body.get("user_id")).first()
    if user is None:
        return failure_response("User not found")
    elif body.get("type") == "student":
        course.students.append(user)
    elif body.get("type") == "instructor":
        course.instructors.append(user)
    else:
        return failure_response("Invalid type", 400)
    
    db.session.commit()

    course = Course.query.filter_by(id=course_id).first()
    
    return success_response(course.serialize())

@app.route("/api/courses/<int:course_id>/drop/", methods=["DELETE"])
def drop_user_from_course(course_id):
    """Drop a user from a course"""
    course = Course.query.filter_by(id=course_id).first()
    if course is None:
        return failure_response("Course not found")
    
    body = json.loads(request.data)
    user = User.query.filter_by(id=body.get("user_id")).first()
    if user is None:
        return failure_response("User not found")
    
    if body.get("type") == "student":
        course.students.remove(user)
    elif body.get("type") == "instructor":
        course.instructors.remove(user) 

    db.session.commit()
    return success_response(course.serialize())

# -- ASSIGNMENT ROUTES ------------------------------------------------------

@app.route("/api/courses/<int:course_id>/assignment/", methods=["POST"])
def create_assignment(course_id):
    """Create an assignment for a course"""
    course = Course.query.filter_by(id=course_id).first()
    if course is None:
        return failure_response("Course not found")

    body = json.loads(request.data)
    if not body.get("title") or not body.get("due_date"):
        return failure_response("Missing required fields", 400)

    try:
        due_date = body.get("due_date")
        new_assignment = Assignment(
            title=body.get("title"),
            due_date=due_date,
            course_id=course_id
        )
        db.session.add(new_assignment)
        db.session.commit()
        return success_response(new_assignment.serialize(), 201)
    except (ValueError, TypeError):
        return failure_response("Invalid timestamp format", 400)
    
@app.route("/api/assignments/<int:assignment_id>/", methods=["POST"])
def update_assignment(assignment_id):
    """Update an assignment"""
    assignment = Assignment.query.filter_by(id=assignment_id).first()
    if assignment is None:
        return failure_response("Assignment not found")
    
    body = json.loads(request.data)
    if not body.get("title") or not body.get("due_date"):
        return failure_response("Missing required fields", 400)
    
    assignment.title = body.get("title")
    assignment.due_date = body.get("due_date")  

    db.session.commit()
    return success_response(assignment.serialize())

@app.route("/api/logout/", methods=["POST"])
def logout():
    """Logout the current user"""
    session.pop("user_id", None)
    return success_response({"message": "Successfully logged out"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
