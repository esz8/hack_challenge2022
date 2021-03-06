from unittest.result import failfast
from db import db
from db import User
from db import Cache
from flask import Flask
from flask import request
import json
import users_dao
from datetime import datetime
# import datetime
import time


app = Flask(__name__)
db_filename = "geocache.db"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///%s" % db_filename
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = True

db.init_app(app)
with app.app_context():
    db.drop_all()
    db.create_all()

# Generalized response formats
def success_response(data, code=200):
    """
    Generalized success response function
    """
    return json.dumps(data), code

def failure_response(message, code=404):
    """
    Generalized failure response function
    """
    return json.dumps({"error": message}), code

def extract_token(request):
    """
    Extracts the token from the header of a request
    Bearer is the type of token we're returning
    """
    auth_header= request.headers.get("Authorization")

    if auth_header is None:
        return False, json.dumps({"Missing authorization header"})
    
    bearer_token = auth_header.replace("Bearer", "").strip()

    return True, bearer_token


# -- User ROUTES ------------------------------------------------------

# Route 1: Get a specific user
@app.route("/api/users/<int:user_id>/")
def get_user(user_id):
    """
    Endpoint for getting user by id
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")
    return success_response(user.serialize())

# Route 2: Register a new user
@app.route("/register/", methods=["POST"])
def register_user():
    """
    Endpoint for registering/creating a new user
    """
    body = json.loads(request.data)
    email = body.get("email")
    password = body.get("password")
    if email is None or password is None:
        return failure_response("Missing email or password")
    name = body.get("name")
    if name is None:
        return failure_response("Enter valid name!", 400)
    username = body.get("username")
    if username is None:
        return failure_response("Enter valid username!", 400)

    was_successful, user = users_dao.create_user(name, username, email, password)

    if not was_successful:
        return failure_response("Username already taken!")

    return success_response(
        {
        "session_token": user.session_token,
        "session_expiration": str(user.session_expiration),
        "update_token": user.update_token
        }, 201  
    )

# Route 3: Logging in a user
@app.route("/login/", methods=["POST"])
def login():
    """
    Endpoint for logging in a user
    """
    body = json.loads(request.data)

    username = body.get("username")
    if username is None:
        return failure_response("Enter your username!", 400)
    password = body.get("password")
    if password is None:
        return failure_response("Enter your password!", 400)
    
    was_successful, user = users_dao.verify_credentials(username, password)

    if not was_successful:
        return failure_response("Incorrect username or password", 401)
    
    user.renew_session()
    db.session.commit()

    return success_response(
        {
        "session_token": user.session_token,
        "session_expiration": str(user.session_expiration),
        "update_token": user.update_token
        },
    )

# Route 4: Update a user's session
@app.route("/session/", methods=["POST"])
def update_session():
    """
    Endpoint for updating a user's session
    """
    was_successful, update_token = extract_token(request)

    if not was_successful:
        return update_token
    
    try:
        user = users_dao.renew_session(update_token)
    except Exception as e:
        return failure_response(f"Invalid update token: {str(e)}")

    return success_response(
        {
        "session_token": user.session_token,
        "session_expiration": str(user.session_expiration),
        "update_token": user.update_token
        }, 201 
    )

# Route 5: Logging out a user
@app.route("/logout/", methods=["POST"])
def logout():
    """
    Endpoint for logging out a user
    """
    was_successful, session_token = extract_token(request)

    if not was_successful:
        return session_token
    
    user = users_dao.get_user_by_session_token(session_token)

    if not user or not user.verify_session_token(session_token):
        return failure_response("Invalid session token")

    user.session_expiration = datetime.now()
    db.session.commit()

    return success_response({
        "message": "You have successfully logged out"
    })

# Route 6: Delete a user by id
@app.route("/api/users/<int:user_id>/", methods=["DELETE"])
def delete_user(user_id):
    """
    Endpoint for deleting a user by id
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")

    user.deactivated = True
    db.session.commit()
    return success_response(user.serialize())


# -- Cache ROUTES ------------------------------------------------------ 

# Route 7: Get all caches
@app.route("/api/caches/")
def get_all_caches():
    """
    Endpoint for getting all caches
    """
    caches = []
    for cache in Cache.query.all():
        caches.append(cache.serialize())
    return success_response({"caches": caches})

# Route 8: Get all caches for a user (that they created)
@app.route("/api/caches/<username>/")
def get_cache(username):
    """
    Endpoint for getting all caches for a specific user (that they created)
    """
    user = User.query.filter_by(username=username).first()
    if user is None:
        return failure_response("User not found!", 404)

    caches = []
    for cache in Cache.query.filter_by(created_by=username):
        caches.append(cache.serialize())
    return success_response({"my_caches": caches})

# Route 9: Get all caches for a user (that they completed)
@app.route("/api/caches/<int:user_id>/completed/")
def get_completed_cache(user_id):
    """
    Endpoint for getting all caches for a specific user (that they completed)
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")
    
    caches = []
    for cache in user.caches_completed:
        caches.append(cache.serialize())
    return success_response({"completed_caches": caches})

# Route 10: Get all caches for a user (that they favorited)
@app.route("/api/caches/<int:user_id>/favorited/")
def get_favorited_cache(user_id):
    """
    Endpoint for getting  fall caches for a specific user (that they favorited)
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")
    
    caches = []
    for cache in user.caches_favorited:
        caches.append(cache.serialize())
    return success_response({"favorite_caches": caches})

# Route 11: Get caches that follow a certain category (size, difficulty, etc)
# How would we do something like get all caches closest to me (some kind of sorting)
# what i could do is make every category 1-5 so i could sort it based on numerical order
# Categories:
# recently addded (date_created), location (maybe add like "distance from me"),
# size, difficulty, terrain
@app.route("/api/caches/<category>/<item>/")
def get_conditional_cache(category, item):
    """
    Endpoint for getting all caches that follow a certain category
    """
    caches = []
    kwargs = {category:item}
    for cache in Cache.query.filter_by(**kwargs):
        caches.append(cache.serialize())
    return success_response({"caches": caches})

# Route 12: Create a cache (associated with a specific user)
@app.route("/api/caches/<int:user_id>/", methods=["POST"])
def create_cache(user_id):
    """
    Endpoint for creating a cache for a user
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found")

    body = json.loads(request.data)
    name = body.get("name")
    if name is None:
        return failure_response("Enter valid name", 400)
    created_by = body.get("created_by")
    if created_by != user.username:
        return failure_response("Incorrect username", 400)
    location = body.get("location")
    if location is None:
        return failure_response("Enter valid location", 400)
    description = body.get("description")
    if description is None:
        return failure_response("Enter valid description", 400)
    hint = body.get("hint")
    size = body.get("size")
    difficulty = body.get("difficulty")
    terrain = body.get("terrain")
    
    last_found = "no finds yet!"
    ts = int(time.time())
    date_created = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    
    new_cache = Cache(
        name=name,
        created_by=created_by,
        location=location,
        description=description,
        hint=hint,
        size=size,
        difficulty=difficulty,
        terrain=terrain,
        last_found=last_found,
        date_created=date_created,
        user_id=user_id
    )

    db.session.add(new_cache)
    db.session.commit()
    return success_response(new_cache.serialize(), 201)

# Route 13: Add a cache to a specific user's completed_caches
@app.route("/api/caches/<int:user_id>/completed/add/", methods=["POST"])
def add_cache(user_id):
    """
    Endpoint for adding a cache to a specific user's completed caches or favorites
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")
    
    body = json.loads(request.data)
    cache_id = body.get("cache_id")
    if cache_id is None:
        return failure_response("Enter valid cache!", 400)
    
    cache = Cache.query.filter_by(id=cache_id).first()
    ts = int(time.time())
    cache.last_found = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    user.caches_completed.append(cache)
    db.session.commit()
    return success_response({"completed_cache": cache.serialize()})

# Route 14: Add a cache to a specific user's favorites
@app.route("/api/caches/<int:user_id>/favorited/add/", methods=["POST"])
def add_favorite(user_id):
    """
    Endpoint for adding a cache to a user's favorited caches
    """
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return failure_response("User not found!")
    
    body = json.loads(request.data)
    cache_id = body.get("cache_id")
    if cache_id is None:
        return failure_response("Enter valid cache!", 400)
    
    cache = Cache.query.filter_by(id=cache_id).first()
    user.caches_favorited.append(cache)
    db.session.commit()
    return success_response({"favorited_cache":cache.serialize()})

# Route 15: Delete cache by id
@app.route("/api/caches/<cache_id>/", methods=["DELETE"])
def delete_cache(cache_id):
    """
    Endpoint for deleting a cache
    """
    cache = Cache.query.filter_by(id=cache_id).first()
    if cache is None:
        return failure_response("Cache not found!")

    db.session.delete(cache)
    db.session.commit()
    return success_response(cache.serialize())


# -- Testing ROUTES ------------------------------------------------------

# Route 16: Get all users
@app.route("/api/users/")
def get_all_users():
    """
    Endpoint for getting all users
    """
    users = []
    for user in User.query.filter_by(deactivated=False).all():
        users.append(user.serialize())
    return success_response({"users": users})



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
