import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from functools import wraps
import requests

app = Flask(__name__)

# ============================================
# 환경 변수 및 설정
# ============================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a7f64f642a64bca92b3aa451e796a82f7d80b97052886744')

# 데이터베이스 설정 (PostgreSQL/SQLite)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    print(f"Using PostgreSQL: {DATABASE_URL[:30]}...")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///website.db'
    print("Using SQLite for local development")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# 파일 업로드 설정
UPLOAD_FOLDER = 'static/uploads'
THUMBNAIL_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'thumbnails')
LOCAL_VIDEO_FOLDER = os.path.join('static', 'uploads', 'videos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAIL_UPLOAD_FOLDER'] = THUMBNAIL_UPLOAD_FOLDER
app.config['LOCAL_VIDEO_FOLDER'] = LOCAL_VIDEO_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAX_LOCAL_VIDEO_SIZE'] = 100 * 1024 * 1024

# 폴더 생성
for folder in [UPLOAD_FOLDER, THUMBNAIL_UPLOAD_FOLDER, LOCAL_VIDEO_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 관리자 설정
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

db = SQLAlchemy(app)

# ============================================
# 데이터베이스 모델
# ============================================
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship('PostImage', backref='post', lazy=True, cascade='all, delete-orphan')

class PostImage(db.Model):
    __tablename__ = 'post_image'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    is_primary = db.Column(db.Boolean, default=False)
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)
    answered = db.Column(db.Boolean, default=False)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    author = db.Column(db.String(100), nullable=False, default='앙상블 다유')
    platform = db.Column(db.String(20), nullable=False)
    video_id = db.Column(db.String(50), nullable=True)
    external_url = db.Column(db.String(500), nullable=True)
    video_filename = db.Column(db.String(255), nullable=True)
    thumbnail_filename = db.Column(db.String(255), nullable=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    duration = db.Column(db.String(20), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    performance_date = db.Column(db.Date, nullable=True)
    tags = db.Column(db.String(500), nullable=True)
    view_count = db.Column(db.Integer, default=0)
    like_count = db.Column(db.Integer, default=0)
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)

# 데이터베이스 초기화
with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating database tables: {e}")

# ============================================
# 유틸리티 함수들
# ============================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('관리자 권한이 필요합니다.')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def extract_date_from_content(content):
    """본문에서 날짜 추출"""
    if not content:
        return None
    
    first_part = content[:50]
    date_patterns = [
        r'(\d{4})[년\.\-/]\s*(\d{1,2})[월"\.\-/]\s*(\d{1,2})[일]?',
        r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})',
        r'(\d{1,2})[월"\.\-/]\s*(\d{1,2})[일]?(?:\s|$|[^\d])'
    ]
    
    for pattern_index, pattern in enumerate(date_patterns):
        matches = re.findall(pattern, first_part)
        if matches:
            match = matches[0]
            try:
                if pattern_index in [0, 1]:
                    year, month, day = int(match[0]), int(match[1]), int(match[2])
                else:
                    month, day = int(match[0]), int(match[1])
                    year = datetime.now().year
                
                if 1 <= month <= 12 and 1 <= day <= 31 and 2020 <= year <= 2030:
                    try:
                        return datetime(year, month, day)
                    except ValueError:
                        continue
            except (ValueError, IndexError):
                continue
    
    return None

def get_display_date(post):
    """게시글 표시용 날짜 반환"""
    try:
        extracted_date = extract_date_from_content(post.content)
        if extracted_date:
            return extracted_date + timedelta(days=1)
        return post.date_posted
    except:
        return post.date_posted

def get_post_images(post):
    """게시글의 모든 이미지를 순서대로 가져오기"""
    try:
        return PostImage.query.filter_by(post_id=post.id).order_by(PostImage.display_order, PostImage.id).all()
    except:
        return []

def get_primary_image(post):
    """게시글의 대표 이미지 가져오기"""
    try:
        primary = PostImage.query.filter_by(post_id=post.id, is_primary=True).first()
        if primary:
            return primary
        
        first_image = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.display_order, PostImage.id).first()
        if first_image:
            return first_image
        
        if hasattr(post, 'image_filename') and post.image_filename:
            return type('obj', (object,), {'filename': post.image_filename, 'is_primary': True})()
        
        return None
    except:
        return None

def get_image_count(post):
    """게시글의 이미지 개수"""
    try:
        count = PostImage.query.filter_by(post_id=post.id).count()
        if hasattr(post, 'image_filename') and post.image_filename and count == 0:
            count = 1
        return count
    except:
        return 0

def save_post_images(post_id, image_files):
    """게시글의 여러 이미지를 저장"""
    saved_images = []
    
    for index, image_file in enumerate(image_files):
        if image_file and image_file.filename != '' and allowed_file(image_file.filename):
            try:
                filename = secure_filename(image_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_extension = os.path.splitext(filename)[1].lower()
                new_filename = f"post_{post_id}_{timestamp}_{index}{file_extension}"
                
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                image_file.save(filepath)
                
                post_image = PostImage(
                    post_id=post_id,
                    filename=new_filename,
                    display_order=index,
                    is_primary=(index == 0)
                )
                db.session.add(post_image)
                saved_images.append(new_filename)
            except Exception as e:
                print(f"이미지 저장 오류: {e}")
                continue
    
    return saved_images

def delete_post_images(post_id):
    """게시글의 모든 이미지 삭제"""
    try:
        images = PostImage.query.filter_by(post_id=post_id).all()
        for image in images:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            db.session.delete(image)
        return True
    except Exception as e:
        print(f"이미지 삭제 오류: {e}")
        return False

# 비디오 관련 유틸리티
def extract_youtube_video_id(url):
    """YouTube URL에서 비디오 ID 추출"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_vimeo_video_id(url):
    """Vimeo URL에서 비디오 ID 추출"""
    pattern = r'vimeo\.com\/(?:.*\/)?(\d+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_video_embed_url(video):
    """비디오 임베드 URL 생성"""
    if video.platform == 'youtube':
        return f"https://www.youtube.com/embed/{video.video_id}"
    elif video.platform == 'vimeo':
        return f"https://player.vimeo.com/video/{video.video_id}"
    elif video.platform == 'local':
        return url_for('static', filename=f'uploads/videos/{video.video_filename}')
    return None

def get_video_thumbnail_url(video):
    """비디오 썸네일 URL"""
    if video.thumbnail_filename:
        return url_for('static', filename=f'uploads/thumbnails/{video.thumbnail_filename}')
    elif video.platform == 'youtube' and video.video_id:
        return f"https://img.youtube.com/vi/{video.video_id}/hqdefault.jpg"
    return None

# ============================================
# Context Processor
# ============================================
@app.context_processor
def inject_global_vars():
    return dict(
        is_admin=session.get('is_admin', False),
        get_display_date=get_display_date,
        extract_date_from_content=extract_date_from_content,
        get_post_images=get_post_images,
        get_primary_image=get_primary_image,
        get_image_count=get_image_count,
        get_video_embed_url=get_video_embed_url,
        get_video_thumbnail_url=get_video_thumbnail_url
    )

# ============================================
# 기본 페이지 라우트
# ============================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/greeting')
def greeting():
    return render_template('greeting.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/members')
def members():
    return render_template('members.html')

@app.route('/healingconcert')
def healingconcert():
    return render_template('healingconcert.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        
        if name and email and message:
            contact_entry = Contact(name=name, email=email, message=message)
            db.session.add(contact_entry)
            db.session.commit()
            flash('문의가 접수되었습니다!')
        else:
            flash('모든 필드를 입력해주세요.')
        
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# ============================================
# 게시판 라우트
# ============================================
@app.route('/board')
def board():
    try:
        posts = Post.query.order_by(Post.date_posted.desc()).all()
        return render_template('board.html', posts=posts)
    except Exception as e:
        print(f"Board error: {e}")
        flash('게시판을 불러오는 중 오류가 발생했습니다.')
        return render_template('board.html', posts=[])

@app.route('/post/<int:post_id>')
def view_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        images = get_post_images(post)
        return render_template('post_detail.html', post=post, images=images)
    except Exception as e:
        print(f"Post view error: {e}")
        flash('게시글을 불러올 수 없습니다.')
        return redirect(url_for('board'))

@app.route('/write', methods=['GET', 'POST'])
@admin_required
def write_post():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            author = request.form.get('author', '').strip()
            
            if not all([title, content, author]):
                flash('모든 필드를 입력해주세요.')
                return redirect(request.url)
            
            new_post = Post(title=title, content=content, author=author)
            db.session.add(new_post)
            db.session.flush()
            
            # 다중 이미지 처리
            image_files = request.files.getlist('images')
            if image_files:
                save_post_images(new_post.id, image_files)
            
            # 단일 이미지 처리 (하위 호환)
            if 'image' in request.files:
                single_image = request.files['image']
                if single_image and single_image.filename != '' and allowed_file(single_image.filename):
                    filename = secure_filename(single_image.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    file_extension = os.path.splitext(filename)[1].lower()
                    new_filename = f"single_{timestamp}{file_extension}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                    single_image.save(filepath)
                    new_post.image_filename = new_filename
            
            db.session.commit()
            flash('게시글이 작성되었습니다!')
            return redirect(url_for('board'))
            
        except Exception as e:
            print(f"Write post error: {e}")
            db.session.rollback()
            flash('게시글 작성 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('write.html')

@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        try:
            post.title = request.form.get('title', '').strip()
            post.content = request.form.get('content', '').strip()
            post.author = request.form.get('author', '').strip()
            
            # 새 이미지 처리
            image_files = request.files.getlist('images')
            if image_files and any(f.filename for f in image_files):
                delete_post_images(post.id)
                save_post_images(post.id, image_files)
            
            db.session.commit()
            flash('게시글이 수정되었습니다!')
            return redirect(url_for('view_post', post_id=post.id))
            
        except Exception as e:
            print(f"Edit post error: {e}")
            db.session.rollback()
            flash('게시글 수정 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('edit_post.html', post=post)

@app.route('/delete/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        delete_post_images(post.id)
        
        if post.image_filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        db.session.delete(post)
        db.session.commit()
        flash('게시글이 삭제되었습니다!')
    except Exception as e:
        print(f"Delete post error: {e}")
        db.session.rollback()
        flash('게시글 삭제 중 오류가 발생했습니다.')
    
    return redirect(url_for('board'))

# ============================================
# 포트폴리오 (비디오) 라우트
# ============================================
@app.route('/portfolio')
def portfolio():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 9
        
        videos_paginated = Video.query.order_by(Video.date_uploaded.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # 각 비디오의 본문에서 날짜 추출
        for video in videos_paginated.items:
            if video.description:
                date_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', video.description)
                if date_match:
                    try:
                        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                        original_date = datetime(year, month, day)
                        next_day = original_date + timedelta(days=1)
                        video.display_date = next_day.strftime('%Y-%m-%d')
                    except ValueError:
                        video.display_date = '날짜 없음'
                else:
                    video.display_date = '날짜 없음'
            else:
                video.display_date = '날짜 없음'
        
        return render_template('portfolio.html', videos=videos_paginated.items, pagination=videos_paginated)
    except Exception as e:
        print(f"Portfolio error: {e}")
        flash('포트폴리오를 불러오는 중 문제가 발생했습니다.')
        return render_template('portfolio.html', videos=[], pagination=None)

@app.route('/video/<int:video_id>')
def view_video(video_id):
    try:
        video = Video.query.get_or_404(video_id)
        video.view_count = (video.view_count or 0) + 1
        db.session.commit()
        
        # 관련 비디오
        related_videos = Video.query.filter(Video.id != video.id).order_by(Video.date_uploaded.desc()).limit(4).all()
        
        return render_template('video_detail.html', video=video, related_videos=related_videos)
    except Exception as e:
        print(f"Video view error: {e}")
        flash('영상을 불러올 수 없습니다.')
        return redirect(url_for('portfolio'))

@app.route('/add_video', methods=['GET', 'POST'])
@admin_required
def add_video():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            author = request.form.get('author', '앙상블 다유').strip()
            platform = request.form.get('platform', 'youtube')
            video_url = request.form.get('video_url', '').strip()
            
            if not title or not video_url:
                flash('영상 제목과 URL을 입력해주세요.')
                return redirect(request.url)
            
            video_id = None
            if platform == 'youtube':
                video_id = extract_youtube_video_id(video_url)
                if not video_id:
                    flash('올바른 YouTube URL을 입력해주세요.')
                    return redirect(request.url)
            elif platform == 'vimeo':
                video_id = extract_vimeo_video_id(video_url)
                if not video_id:
                    flash('올바른 Vimeo URL을 입력해주세요.')
                    return redirect(request.url)
            
            video = Video(
                title=title,
                description=description,
                author=author,
                platform=platform,
                video_id=video_id,
                external_url=video_url
            )
            
            if hasattr(video, 'tags'):
                video.tags = request.form.get('tags', '').strip()
            
            db.session.add(video)
            db.session.commit()
            
            flash('영상이 성공적으로 추가되었습니다!')
            return redirect(url_for('portfolio'))
        except Exception as e:
            print(f"Add video error: {e}")
            flash('영상 추가 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('add_video.html')

@app.route('/edit_video/<int:video_id>', methods=['GET', 'POST'])
@admin_required
def edit_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    if request.method == 'POST':
        try:
            video.title = request.form.get('title', '').strip()
            video.description = request.form.get('description', '').strip()
            video.author = request.form.get('author', '앙상블 다유').strip()
            
            if hasattr(video, 'tags'):
                video.tags = request.form.get('tags', '').strip()
            
            db.session.commit()
            flash('영상 정보가 성공적으로 수정되었습니다!')
            return redirect(url_for('view_video', video_id=video.id))
        except Exception as e:
            print(f"Edit video error: {e}")
            flash('영상 수정 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('edit_video.html', video=video)

@app.route('/delete_video/<int:video_id>', methods=['POST'])
@admin_required
def delete_video(video_id):
    try:
        video = Video.query.get_or_404(video_id)
        video_title = video.title
        
        if hasattr(video, 'video_filename') and video.video_filename:
            video_path = os.path.join(app.config.get('LOCAL_VIDEO_FOLDER', ''), video.video_filename)
            if os.path.exists(video_path):
                os.remove(video_path)
        
        if hasattr(video, 'thumbnail_filename') and video.thumbnail_filename:
            thumbnail_path = os.path.join(app.config.get('THUMBNAIL_UPLOAD_FOLDER', ''), video.thumbnail_filename)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        
        db.session.delete(video)
        db.session.commit()
        
        flash(f'영상 "{video_title}"이 성공적으로 삭제되었습니다!')
    except Exception as e:
        print(f"Delete video error: {e}")
        flash('영상 삭제 중 오류가 발생했습니다.')
    
    return redirect(url_for('portfolio'))

# ============================================
# 관리자 라우트
# ============================================
@app.route('/admin')
def admin_redirect():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
@app.route('/secret-admin-access-2025', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('관리자로 로그인되었습니다.')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('아이디 또는 비밀번호가 잘못되었습니다.')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('로그아웃되었습니다.')
    return redirect(url_for('home'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    contacts = Contact.query.order_by(Contact.date_sent.desc()).all()
    return render_template('admin.html', contacts=contacts)

@app.route('/admin/mark_answered/<int:contact_id>')
@admin_required
def mark_answered(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.answered = True
    db.session.commit()
    flash('답변완료로 처리되었습니다.')
    return redirect(url_for('admin_dashboard'))

# ============================================
# 에러 핸들러
# ============================================
@app.errorhandler(404)
def page_not_found(e):
    try:
        return render_template('404.html'), 404
    except:
        return '''
        <div style="text-align: center; padding: 100px 20px; font-family: Arial, sans-serif;">
            <h1 style="font-size: 5em; color: #8b7355; margin: 0;">404</h1>
            <p style="font-size: 1.2em; color: #666;">페이지를 찾을 수 없습니다.</p>
            <a href="/" style="color: #8b7355; text-decoration: none; font-size: 1.1em;">홈으로 돌아가기</a>
        </div>
        ''', 404

@app.errorhandler(500)
def internal_server_error(e):
    try:
        return render_template('500.html'), 500
    except:
        return '''
        <div style="text-align: center; padding: 100px 20px; font-family: Arial, sans-serif;">
            <h1 style="font-size: 5em; color: #dc3545; margin: 0;">500</h1>
            <p style="font-size: 1.2em; color: #666;">서버 오류가 발생했습니다.</p>
            <a href="/" style="color: #8b7355; text-decoration: none; font-size: 1.1em;">홈으로 돌아가기</a>
        </div>
        ''', 500

# ============================================
# API 라우트
# ============================================
@app.route('/api/video/<int:video_id>')
def get_video_info(video_id):
    """AJAX용 비디오 정보 API"""
    try:
        video = Video.query.get_or_404(video_id)
        
        video_data = {
            'id': video.id,
            'title': video.title,
            'description': video.description,
            'author': video.author,
            'platform': video.platform,
            'video_id': video.video_id,
            'external_url': video.external_url,
            'duration': video.duration,
            'view_count': video.view_count,
            'like_count': video.like_count
        }
        
        if video.platform == 'youtube':
            video_data['video_url'] = f"https://www.youtube.com/embed/{video.video_id}"
        elif video.platform == 'vimeo':
            video_data['video_url'] = f"https://player.vimeo.com/video/{video.video_id}"
        elif video.platform == 'local' and video.video_filename:
            video_data['video_url'] = url_for('static', filename=f'uploads/videos/{video.video_filename}')
        
        return jsonify(video_data)
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/video/<int:video_id>/view', methods=['POST'])
def update_view_count(video_id):
    """조회수 업데이트 API"""
    try:
        video = Video.query.get_or_404(video_id)
        video.view_count += 1
        db.session.commit()
        return jsonify({'success': True, 'view_count': video.view_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/video/<int:video_id>/like', methods=['POST'])
def like_video_api(video_id):
    """좋아요 API"""
    try:
        video = Video.query.get_or_404(video_id)
        video.like_count += 1
        db.session.commit()
        return jsonify({'success': True, 'like_count': video.like_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# 디버그 라우트
# ============================================
@app.route('/debug/routes')
def debug_routes():
    """모든 등록된 라우트 확인"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify({'routes': routes})

@app.route('/debug/templates')
def debug_templates():
    """템플릿 폴더 파일 확인"""
    results = {
        'template_folder': app.template_folder,
        'template_folder_absolute': os.path.abspath(app.template_folder),
        'exists': os.path.exists(app.template_folder),
        'files': []
    }
    
    if os.path.exists(app.template_folder):
        try:
            for root, dirs, files in os.walk(app.template_folder):
                for file in files:
                    filepath = os.path.join(root, file)
                    results['files'].append(filepath)
        except Exception as e:
            results['files_error'] = str(e)
    
    return jsonify(results)

@app.route('/debug/db')
def debug_db():
    """데이터베이스 연결 확인"""
    try:
        db.session.execute(db.text('SELECT 1'))
        posts_count = Post.query.count()
        videos_count = Video.query.count()
        contacts_count = Contact.query.count()
        
        return jsonify({
            'status': 'success',
            'database': 'connected',
            'posts_count': posts_count,
            'videos_count': videos_count,
            'contacts_count': contacts_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

# ============================================
# 앱 실행
# ============================================
if __name__ == '__main__':
    app.run(debug=True)

print("="*50)
print("Render.com 배포용 Flask 앱 초기화 완료!")
print("지원 기능:")
print("  - 게시판 (다중 이미지 지원)")
print("  - 포트폴리오 (YouTube/Vimeo/로컬 비디오)")
print("  - 연락처 폼")
print("  - 관리자 기능")
print("="*50)