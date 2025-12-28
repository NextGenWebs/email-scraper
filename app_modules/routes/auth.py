"""
Authentication routes (login, signup, logout)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from app_modules.extensions import db
from app_modules.models import User, seed_default_email_filters_for_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # Check if user can access the system
            can_access, message = user.can_access()
            if not can_access:
                flash(message, 'error')
                return redirect(url_for('auth.login'))
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            login_user(user)
            return redirect(url_for('views.dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('auth.signup'))
        
        # Check if this is the first user (auto-approve and make admin)
        is_first_user = User.query.count() == 0
        
        user = User(email=email)
        user.set_password(password)
        
        if is_first_user:
            # First user is automatically admin and approved
            user.is_admin = True
            user.is_approved = True
            db.session.add(user)
            db.session.commit()
            seed_default_email_filters_for_user(user.id)
            login_user(user)
            flash('Welcome! You are the first user and have been granted admin privileges.', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            # Regular users need approval
            user.is_approved = False
            db.session.add(user)
            db.session.commit()
            seed_default_email_filters_for_user(user.id)
            flash('Account created! Please wait for administrator approval before you can login.', 'info')
            return redirect(url_for('auth.login'))
    
    return render_template('signup.html')
    
    return render_template('signup.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
