from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory, abort
from flask_pymongo import PyMongo
from bson import ObjectId
from datetime import datetime
import os
import pymongo
import re
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

def datetimeformat(value, format='%b %d, %Y'):
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d')
    return value.strftime(format)

app = Flask(__name__)
app.jinja_env.filters['datetimeformat'] = datetimeformat
app.config['MONGO_URI'] = 'mongodb+srv://chesstournament:chesstournament@crypticloud.be143.mongodb.net/chessdb?retryWrites=true&w=majority&appName=CryptiCloud'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg'}

mongo = PyMongo(app)

class Organizer:
    def __init__(self, username, password, name, type, location, contact=None, is_admin=False):
        self.username = username
        self.password_hash = generate_password_hash(password)
        self.name = name
        self.type = type
        self.location = location
        self.contact = contact or {}
        self.is_admin = is_admin
        self.created_at = datetime.utcnow()

    @staticmethod
    def get_collection():
        return mongo.db.organizers

class Tournament:
    def __init__(self, organizer_id, title, fide_status, prize_details, 
                 age_categories, gender_category, mode, format, state, dates):
        self.organizer_id = organizer_id
        self.title = title
        self.fide_status = fide_status
        self.prize_details = prize_details
        self.age_categories = age_categories
        self.gender_category = gender_category
        self.mode = mode
        self.format = format
        self.state = state
        self.dates = dates
        self.description = ''
        self.files = []
        self.featured = False  # New field to determine if tournament should be shown on home page
        self.created_at = datetime.utcnow()

    @staticmethod
    def get_collection():
        return mongo.db.tournaments

@app.route('/tournament/<tournament_id>')
def tournament_detail(tournament_id):
    tournament = Tournament.get_collection().find_one({'_id': ObjectId(tournament_id)})
    if not tournament:
        abort(404)
    
    organizer = Organizer.get_collection().find_one({'_id': ObjectId(tournament['organizer_id'])})
    return render_template('tournament_detail.html', 
                         tournament=tournament,
                         organizer=organizer)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def home():
    filters = {}
    
    # If no search filters are applied, only show featured tournaments
    if not any(key in request.args for key in ['state', 'format', 'fide', 'gender', 'age', 'mode', 'start_date', 'end_date']):
        filters['featured'] = True
    
    # Apply filters only if they are provided
    if request.args.get('state'):
        filters['state'] = request.args.get('state')
    if request.args.get('format'):
        filters['format'] = request.args.get('format')
    if request.args.get('fide') == 'yes':
        filters['fide_status'] = True
    if request.args.get('gender') and request.args.get('gender') != 'Open':
        filters['gender_category'] = {'$in': [request.args.get('gender'), 'Open']}
    if request.args.getlist('age'):
        filters['age_categories'] = {'$all': request.args.getlist('age')}
    if request.args.get('mode'):
        filters['mode'] = request.args.get('mode')
    
    # Date filtering
    if request.args.get('start_date') and request.args.get('end_date'):
        filters['dates'] = {
            '$gte': datetime.strptime(request.args['start_date'], '%Y-%m-%d'),
            '$lte': datetime.strptime(request.args['end_date'], '%Y-%m-%d')
        }
    
    # Fetch tournaments based on filters
    tournaments = Tournament.get_collection().find(filters).sort('created_at', -1)
    current_year = datetime.now().year
    return render_template('home.html', tournaments=tournaments, current_year=current_year)

# Authentication routes
# In the registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')

        # Password complexity validation
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        if len(password) < 8:
            flash('Password must be at least 8 characters')
            return redirect(url_for('register'))
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])', password):
            flash('Password must contain: 1 uppercase, 1 lowercase, 1 number, 1 special character')
            return redirect(url_for('register'))
        if username.lower() in password.lower():
            flash('Password cannot contain your username')
            return redirect(url_for('register'))
        
        if mongo.db.organizers.find_one({'username': username}):
            flash('Username already exists')
            return redirect(url_for('register'))
        if not email:
            flash('Email is required')
            return redirect(url_for('register'))
        if mongo.db.organizers.find_one({'contact.email': email}):
            flash('Email already registered')
            return redirect(url_for('register'))
        
        organizer = Organizer(
            username=username,
            password=request.form['password'],
            name=request.form['name'],
            type=request.form.get('type'),
            location=request.form.get('location'),
            contact={
                'whatsapp': request.form.get('whatsapp'),
                'email': email
            }
        )
        Organizer.get_collection().insert_one(organizer.__dict__)
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Find the organizer by username
        organizer = Organizer.get_collection().find_one({'username': username})
        
        if organizer and 'password_hash' in organizer and check_password_hash(organizer['password_hash'], password):
            # Set session variables
            session['organizer_id'] = str(organizer['_id'])
            session['is_admin'] = organizer.get('is_admin', False)
            
            # Redirect based on admin status
            if session['is_admin']:
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/organizer-profile', endpoint='organizer_profile')
def organizer_profile():
    if 'organizer_id' not in session:
        return redirect(url_for('login'))
    organizer = Organizer.get_collection().find_one({'_id': ObjectId(session['organizer_id'])})
    tournaments = Tournament.get_collection().find({'organizer_id': session['organizer_id']}).sort('created_at', -1)
    return render_template('organizer_profile.html', organizer=organizer, tournaments=tournaments)

@app.route('/dashboard')
def dashboard():
    if 'organizer_id' not in session:
        return redirect(url_for('login'))
    tournaments = Tournament.get_collection().find({'organizer_id': session['organizer_id']}).sort('created_at', -1)
    return render_template('dashboard.html', tournaments=tournaments)

@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    tournaments = Tournament.get_collection().find().sort('created_at', -1)
    organizers = Organizer.get_collection().find().sort('created_at', -1)
    return render_template('admin_panel.html', tournaments=tournaments, organizers=organizers)

@app.route('/admin/featured', methods=['GET', 'POST'])
def admin_featured():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        featured_ids = request.form.getlist('featured_tournaments')
        # Update all tournaments - set featured=True for selected, False for others
        Tournament.get_collection().update_many(
            {'_id': {'$in': [ObjectId(id) for id in featured_ids]}},
            {'$set': {'featured': True}}
        )
        Tournament.get_collection().update_many(
            {'_id': {'$nin': [ObjectId(id) for id in featured_ids]}},
            {'$set': {'featured': False}}
        )
        flash('Featured tournaments updated successfully!', 'success')
        return redirect(url_for('admin_featured'))
    
    all_tournaments = Tournament.get_collection().find().sort('created_at', -1)
    return render_template('admin_featured.html', all_tournaments=all_tournaments)
@app.route('/create-tournament', methods=['GET', 'POST'])
def create_tournament():
    if 'organizer_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Process start and end dates
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            dates = [start_date, end_date] if start_date != end_date else [start_date]
            
            tournament = Tournament(
                organizer_id=session['organizer_id'],
                title=request.form['title'],
                fide_status=request.form.get('fide_status', 'no') == 'yes',
                prize_details=request.form['prize_details'],
                age_categories=[f"{request.form['min_age']}-{request.form['max_age']}"],
                gender_category=request.form['gender_category'],
                mode=request.form['mode'],
                format=request.form['format'],
                state=request.form['state'],
                dates=dates
            )
            tournament.description = request.form.get('description', '')
            tournament.entry_fee = request.form.get('entry_fee', '0')
            tournament.featured = False  # Default to not featured
            
            if 'file' in request.files:
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    tournament.files.append(filename)
            
            Tournament.get_collection().insert_one(tournament.__dict__)
            flash('Tournament created successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error creating tournament: {str(e)}')
    
    return render_template('create_tournament.html')



def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/logout')
def logout():
    session.pop('organizer_id', None)
    session.pop('is_admin', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Add this after PyMongo initialization
    mongo.db.organizers.create_index([('username', pymongo.ASCENDING)], unique=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Create admin account if not exists
    # Create/update admin account
    Organizer.get_collection().update_many(
        {'is_admin': {'$exists': False}},
        {'$set': {'is_admin': False}}
    )
    
    # Check if admin exists
    admin = Organizer.get_collection().find_one({'username': 'admin'})
    if not admin:
        # Create new admin account
        admin = Organizer(
            username='admin',
            password='admin123',  # Default password
            name='Admin',
            type='admin',
            location='System',
            is_admin=True
        )
        Organizer.get_collection().insert_one(admin.__dict__)
        print('Admin account created successfully!')
    else:
        # Just ensure admin flag is set
        Organizer.get_collection().update_one(
            {'username': 'admin'},
            {'$set': {'is_admin': True}}
        )
        print('Admin account verified!')
    
    app.run(port=1100)
