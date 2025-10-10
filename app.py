import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
from functools import wraps
import requests
import re
import requests
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a7f64f642a64bca92b3aa451e796a82f7d80b97052886744'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.root_path, "website.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 파일 업로드 설정 - Flask 앱 기준 경로 사용
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 제한

# 관리자 계정 설정
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# 허용된 파일 확장자
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# 업로드 폴더 생성
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print(f"업로드 폴더 확인/생성 완료: {app.config['UPLOAD_FOLDER']}")
except Exception as e:
    print(f"업로드 폴더 생성 오류: {e}")
import requests
from urllib.parse import urlparse, parse_qs

# 썸네일 업로드 폴더만 필요 (영상은 외부 플랫폼 사용)
THUMBNAIL_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'thumbnails')
LOCAL_VIDEO_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'videos')  # 작은 로컬 파일용
app.config['THUMBNAIL_UPLOAD_FOLDER'] = THUMBNAIL_UPLOAD_FOLDER
app.config['LOCAL_VIDEO_FOLDER'] = LOCAL_VIDEO_FOLDER
app.config['MAX_LOCAL_VIDEO_SIZE'] = 100 * 1024 * 1024  # 100MB 제한

# 업로드 폴더들 생성
try:
    os.makedirs(THUMBNAIL_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(LOCAL_VIDEO_FOLDER, exist_ok=True)
    print(f"썸네일 폴더 확인/생성 완료: {THUMBNAIL_UPLOAD_FOLDER}")
    print(f"로컬 비디오 폴더 확인/생성 완료: {LOCAL_VIDEO_FOLDER}")
except Exception as e:
    print(f"폴더 생성 오류: {e}")

db = SQLAlchemy(app)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 더 안전한 버전 - import를 함수 상단에 명시

def extract_date_from_content(content):
    """본문에서 날짜를 추출하는 함수 (안전한 버전)"""
    from datetime import datetime as DateTime  # 명확한 이름으로 import
    
    if not content:
        return None
    
    # 본문의 첫 50자에서 검색
    first_part = content[:50]
    
    # 간단한 패턴들만 사용 (안정성 우선)
    date_patterns = [
        # YYYY년 MM월 DD일 형식
        r'(\d{4})[년\.\-/]\s*(\d{1,2})[월"\.\-/]\s*(\d{1,2})[일]?',
        # YYYY-MM-DD 형식
        r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})',
        # MM월 DD일 형식 (현재 연도 사용)
        r'(\d{1,2})[월"\.\-/]\s*(\d{1,2})[일]?(?:\s|$|[^\d])'
    ]
    
    for pattern_index, pattern in enumerate(date_patterns):
        matches = re.findall(pattern, first_part)
        if matches:
            match = matches[0]
            try:
                if pattern_index in [0, 1]:  # 연도가 있는 형식
                    year, month, day = int(match[0]), int(match[1]), int(match[2])
                else:  # 연도가 없는 형식 - 현재 연도 사용
                    month, day = int(match[0]), int(match[1])
                    current_year = DateTime.now().year
                    year = current_year
                
                # 유효한 날짜인지 확인
                if 1 <= month <= 12 and 1 <= day <= 31 and 2020 <= year <= 2030:
                    try:
                        extracted_date = DateTime(year, month, day)
                        return extracted_date
                    except ValueError:
                        continue
                        
            except (ValueError, IndexError):
                continue
    
    return None

def get_display_date(post):
    """게시글 표시용 날짜를 반환하는 함수 (안전한 버전)"""
    try:
        extracted_date = extract_date_from_content(post.content)
        if extracted_date:
            # 공연 다음날로 설정 (+1일)
            return extracted_date + timedelta(days=1)
        else:
            return post.date_posted
    except Exception as e:
        print(f"get_display_date 오류: {e}")
        return post.date_posted
    

def resize_image(filepath, max_size=(800, 600)):    
    """이미지 크기 조정"""
    try:
        # 파일 확장자 확인
        file_extension = os.path.splitext(filepath)[1].lower()
        if file_extension not in ['.jpg', '.jpeg', '.png', '.gif']:
            print(f"지원하지 않는 이미지 형식: {file_extension}")
            return
            
        with Image.open(filepath) as img:
            # 이미지가 너무 크면 리사이징
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # 파일 형식에 따라 저장
                if file_extension in ['.jpg', '.jpeg']:
                    img.save(filepath, 'JPEG', optimize=True, quality=85)
                elif file_extension == '.png':
                    img.save(filepath, 'PNG', optimize=True)
                else:
                    img.save(filepath, optimize=True, quality=85)
                    
                print(f"이미지 리사이징 완료: {filepath}")
            else:
                print(f"이미지 크기가 적절함: {filepath}")
                
    except Exception as e:
        print(f"이미지 리사이징 오류: {e}")

# 관리자 인증 데코레이터
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('관리자 권한이 필요합니다.')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# 데이터베이스 모델
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
class PostImage(db.Model):
    __tablename__ = 'post_image'
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, default=0)  # 표시 순서
    is_primary = db.Column(db.Boolean, default=False)  # 대표 이미지 여부
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 관계 설정
    post = db.relationship('Post', backref=db.backref('images', lazy=True, cascade='all, delete-orphan'))

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)
    answered = db.Column(db.Boolean, default=False)
def get_post_images(post):
    """게시글의 모든 이미지를 순서대로 가져오기"""
    try:
        return PostImage.query.filter_by(post_id=post.id).order_by(PostImage.display_order, PostImage.id).all()
    except:
        return []

def get_primary_image(post):
    """게시글의 대표 이미지 가져오기"""
    try:
        # 먼저 is_primary=True인 이미지 찾기
        primary = PostImage.query.filter_by(post_id=post.id, is_primary=True).first()
        if primary:
            return primary
        
        # 없으면 첫 번째 이미지
        first_image = PostImage.query.filter_by(post_id=post.id).order_by(PostImage.display_order, PostImage.id).first()
        if first_image:
            return first_image
            
        # 새 테이블에 이미지가 없으면 기존 image_filename 사용
        if hasattr(post, 'image_filename') and post.image_filename:
            return type('obj', (object,), {'filename': post.image_filename, 'is_primary': True})()
            
        return None
    except:
        return None

def get_image_count(post):
    """게시글의 이미지 개수"""
    try:
        count = PostImage.query.filter_by(post_id=post.id).count()
        # 기존 image_filename도 카운트
        if hasattr(post, 'image_filename') and post.image_filename and count == 0:
            count = 1
        return count
    except:
        return 0
# 템플릿에서 사용할 전역 변수 및 함수
@app.context_processor
def inject_admin_status():
    return dict(
        is_admin=session.get('is_admin', False),
        get_display_date=get_display_date,
        extract_date_from_content=extract_date_from_content
    )

# 라우트들
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

@app.route('/board')
def board():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('board.html', posts=posts)


# 다중 이미지 처리를 위한 유틸리티 함수들
def save_post_images(post_id, image_files):
    """게시글의 여러 이미지를 저장하는 함수"""
    saved_images = []
    
    for index, image_file in enumerate(image_files):
        if image_file and image_file.filename != '' and allowed_file(image_file.filename):
            try:
                # 안전한 파일명 생성
                filename = secure_filename(image_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_extension = os.path.splitext(filename)[1].lower()
                new_filename = f"post_{post_id}_{timestamp}_{index}{file_extension}"
                
                # 파일 저장
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                image_file.save(filepath)
                
                # 이미지 리사이징 (선택사항)
                try:
                    from PIL import Image
                    with Image.open(filepath) as img:
                        if img.size[0] > 1200 or img.size[1] > 1200:
                            img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                            img.save(filepath, optimize=True, quality=85)
                except Exception as e:
                    print(f"이미지 리사이징 오류: {e}")
                
                # 데이터베이스에 저장
                post_image = PostImage(
                    post_id=post_id,
                    filename=new_filename,
                    display_order=index,
                    is_primary=(index == 0)  # 첫 번째 이미지를 대표 이미지로
                )
                db.session.add(post_image)
                saved_images.append(new_filename)
                
            except Exception as e:
                print(f"이미지 저장 오류: {e}")
                continue
    
    return saved_images

def delete_post_images(post_id):
    """게시글의 모든 이미지를 삭제하는 함수"""
    try:
        images = PostImage.query.filter_by(post_id=post_id).all()
        for image in images:
            # 파일 삭제
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # 데이터베이스에서 삭제
            db.session.delete(image)
        
        return True
    except Exception as e:
        print(f"이미지 삭제 오류: {e}")
        return False
        
# app.py의 write_post 함수를 다음과 같이 디버그 버전으로 교체

@app.route('/write', methods=['GET', 'POST'])
@admin_required
def write_post():
    if request.method == 'POST':
        try:
            print("=== 게시글 작성 시작 ===")
            
            # 폼 데이터 확인
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            author = request.form.get('author', '').strip()
            
            print(f"제목: '{title}'")
            print(f"내용 길이: {len(content)}자")
            print(f"작성자: '{author}'")
            
            # 필수 필드 확인
            if not title:
                flash('제목을 입력해주세요.')
                return redirect(request.url)
            
            if not content:
                flash('내용을 입력해주세요.')
                return redirect(request.url)
                
            if not author:
                flash('작성자를 입력해주세요.')
                return redirect(request.url)
            
            # 이미지 파일 처리
            image_filename = None
            if 'image' in request.files:
                file = request.files['image']
                print(f"업로드된 파일: {file.filename}")
                
                if file and file.filename != '' and allowed_file(file.filename):
                    try:
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        file_extension = os.path.splitext(filename)[1].lower()
                        new_filename = f"{timestamp}{file_extension}"
                        
                        # 업로드 폴더 확인
                        upload_folder = app.config['UPLOAD_FOLDER']
                        print(f"업로드 폴더: {upload_folder}")
                        
                        if not os.path.exists(upload_folder):
                            os.makedirs(upload_folder, exist_ok=True)
                            print("업로드 폴더 생성됨")
                        
                        filepath = os.path.join(upload_folder, new_filename)
                        print(f"저장할 경로: {filepath}")
                        
                        # 파일 저장
                        file.save(filepath)
                        print("파일 저장 완료")
                        
                        # 이미지 리사이징 (선택사항)
                        try:
                            resize_image(filepath)
                            print("이미지 리사이징 완료")
                        except Exception as resize_error:
                            print(f"리사이징 오류: {resize_error}")
                        
                        image_filename = new_filename
                        
                    except Exception as file_error:
                        print(f"파일 처리 오류: {file_error}")
                        flash('이미지 업로드 중 오류가 발생했습니다.')
                        return redirect(request.url)
                else:
                    print("파일이 없거나 허용되지 않는 형식입니다.")
            
            # 데이터베이스 저장
            print("데이터베이스 저장 시작")
            post = Post(title=title, content=content, author=author, image_filename=image_filename)
            print(f"Post 객체 생성: {post}")
            
            db.session.add(post)
            print("세션에 추가됨")
            
            db.session.commit()
            print("커밋 완료")
            
            flash('게시글이 작성되었습니다!')
            return redirect(url_for('board'))
            
        except Exception as e:
            print(f"게시글 작성 오류: {e}")
            import traceback
            traceback.print_exc()  # 전체 오류 스택 출력
            
            db.session.rollback()
            flash('게시글 작성 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    # GET 요청 시
    return render_template('write.html')   
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        
        contact = Contact(name=name, email=email, message=message)
        db.session.add(contact)
        db.session.commit()
        
        flash('문의가 접수되었습니다!')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# 관리자 로그인 페이지 (숨겨진 URL)
@app.route('/secret-admin-access-2025', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('관리자로 로그인되었습니다.')
            return redirect(url_for('admin'))
        else:
            flash('아이디 또는 비밀번호가 잘못되었습니다.')
    
    return render_template('admin_login.html')

# 관리자 로그아웃
@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('로그아웃되었습니다.')
    return redirect(url_for('home'))

# 관리자 페이지 (인증 필요)
@app.route('/admin')
@admin_required
def admin():
    contacts = Contact.query.order_by(Contact.date_sent.desc()).all()
    return render_template('admin.html', contacts=contacts)

# 게시글 상세보기
@app.route('/post/<int:post_id>')
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post_detail.html', post=post)


@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        try:
            post.title = request.form['title']
            post.content = request.form['content']
            post.author = request.form['author']
            
            # 새 이미지가 업로드된 경우
            image_files = request.files.getlist('images')
            if image_files and any(f.filename for f in image_files):
                # 기존 이미지들 삭제
                delete_post_images(post.id)
                
                # 새 이미지들 저장
                saved_images = save_post_images(post.id, image_files)
                print(f"수정 시 저장된 이미지: {saved_images}")
            
            # 기존 단일 이미지 처리 (하위 호환성)
            if 'image' in request.files:
                single_image = request.files['image']
                if single_image and single_image.filename != '' and allowed_file(single_image.filename):
                    # 기존 단일 이미지 삭제
                    if post.image_filename:
                        old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    
                    # 새 단일 이미지 저장
                    filename = secure_filename(single_image.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    file_extension = os.path.splitext(filename)[1].lower()
                    new_filename = f"single_{timestamp}{file_extension}"
                    
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                    single_image.save(filepath)
                    post.image_filename = new_filename
            
            db.session.commit()
            flash('게시글이 수정되었습니다!')
            return redirect(url_for('view_post', post_id=post.id))
            
        except Exception as e:
            print(f"게시글 수정 오류: {e}")
            db.session.rollback()
            flash('게시글 수정 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('edit_post.html', post=post)

# 수정된 게시글 삭제 라우트
@app.route('/delete/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
        # 다중 이미지 삭제
        delete_post_images(post.id)
        
        # 기존 단일 이미지 삭제
        if post.image_filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        # 게시글 삭제
        db.session.delete(post)
        db.session.commit()
        
        flash('게시글이 삭제되었습니다!')
        
    except Exception as e:
        print(f"게시글 삭제 오류: {e}")
        db.session.rollback()
        flash('게시글 삭제 중 오류가 발생했습니다.')
    
    return redirect(url_for('board'))

# 템플릿에서 사용할 함수들을 전역 컨텍스트에 추가
@app.context_processor
def inject_post_functions():
    return dict(
        get_post_images=get_post_images,
        get_primary_image=get_primary_image,
        get_image_count=get_image_count,
        is_admin=session.get('is_admin', False),
        get_display_date=get_display_date,
        extract_date_from_content=extract_date_from_content
    )
# 문의 답변완료 처리
@app.route('/admin/mark_answered/<int:contact_id>')
@admin_required
def mark_answered(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    contact.answered = True
    db.session.commit()
    flash('답변완료로 처리되었습니다.')
    return redirect(url_for('admin'))
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

def get_youtube_video_info(video_id):
    """YouTube oEmbed API를 통해 비디오 정보 가져오기"""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', ''),
                'author': data.get('author_name', ''),
                'thumbnail_url': data.get('thumbnail_url', ''),
                'duration': None,  # oEmbed에서는 제공되지 않음
                'description': f"{data.get('author_name', '')} 채널의 영상"
            }
    except Exception as e:
        print(f"YouTube 정보 가져오기 오류: {e}")
    
    return None

def get_vimeo_video_info(video_id):
    """Vimeo oEmbed API를 통해 비디오 정보 가져오기"""
    try:
        url = f"https://vimeo.com/api/oembed.json?url=https://vimeo.com/{video_id}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', ''),
                'author': data.get('author_name', ''),
                'thumbnail_url': data.get('thumbnail_url', ''),
                'duration': data.get('duration'),
                'description': data.get('description', '')
            }
    except Exception as e:
        print(f"Vimeo 정보 가져오기 오류: {e}")
    
    return None

def download_thumbnail(thumbnail_url, filename):
    """외부 썸네일을 다운로드하여 로컬에 저장"""
    try:
        response = requests.get(thumbnail_url, timeout=10)
        if response.status_code == 200:
            filepath = os.path.join(app.config['THUMBNAIL_UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # 이미지 리사이징
            try:
                from PIL import Image
                with Image.open(filepath) as img:
                    img.thumbnail((640, 360), Image.Resampling.LANCZOS)
                    img.save(filepath, optimize=True, quality=85)
            except Exception as e:
                print(f"썸네일 리사이징 오류: {e}")
            
            return filename
    except Exception as e:
        print(f"썸네일 다운로드 오류: {e}")
    
    return None

# 하이브리드 비디오 데이터베이스 모델
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    author = db.Column(db.String(100), nullable=False, default='앙상블 다유')
    
    # 플랫폼 정보
    platform = db.Column(db.String(20), nullable=False)  # 'youtube', 'vimeo', 'local'
    video_id = db.Column(db.String(50), nullable=True)  # YouTube/Vimeo ID
    external_url = db.Column(db.String(500), nullable=True)  # 원본 URL
    video_filename = db.Column(db.String(255), nullable=True)  # 로컬 파일명
    
    # 썸네일 (로컬 저장 또는 외부 URL)
    thumbnail_filename = db.Column(db.String(255), nullable=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)  # 외부 썸네일 URL
    
    # 메타데이터
    duration = db.Column(db.String(20), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    performance_date = db.Column(db.Date, nullable=True)
    tags = db.Column(db.String(500), nullable=True)
    
    # 통계
    view_count = db.Column(db.Integer, default=0)
    like_count = db.Column(db.Integer, default=0)
    
    # 기타
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)

# 라우트들


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
        
        # 플랫폼별 비디오 URL 설정
        if video.platform == 'youtube':
            video_data['video_url'] = f"https://www.youtube.com/embed/{video.video_id}"
        elif video.platform == 'vimeo':
            video_data['video_url'] = f"https://player.vimeo.com/video/{video.video_id}"
        elif video.platform == 'local' and video.video_filename:
            video_data['video_url'] = url_for('static', filename=f'uploads/videos/{video.video_filename}')
        
        return jsonify(video_data)
        
    except Exception as e:
        print(f"API 오류: {e}")
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

def get_related_videos(current_video, limit=4):
    """관련 영상을 가져오는 함수"""
    try:
        related = []
        
        # 같은 태그를 가진 영상들 우선
        if current_video.tags:
            current_tags = set(tag.strip().lower() for tag in current_video.tags.split(','))
            
            all_videos = Video.query.filter(Video.id != current_video.id).all()
            
            for video in all_videos:
                if video.tags:
                    video_tags = set(tag.strip().lower() for tag in video.tags.split(','))
                    common_tags = current_tags.intersection(video_tags)
                    if common_tags:
                        related.append((video, len(common_tags)))
            
            # 공통 태그 수로 정렬
            related.sort(key=lambda x: x[1], reverse=True)
            related = [video for video, _ in related[:limit]]
        
        # 태그가 없거나 관련 영상이 부족한 경우 최신 영상으로 채움
        if len(related) < limit:
            recent_videos = Video.query.filter(
                Video.id != current_video.id
            ).order_by(Video.date_uploaded.desc()).limit(limit - len(related)).all()
            
            for video in recent_videos:
                if video not in related:
                    related.append(video)
        
        return related[:limit]
        
    except Exception as e:
        print(f"관련 영상 조회 오류: {e}")
        return []

@app.route('/portfolio/search')
def search_videos():
    """영상 검색 API"""
    query = request.args.get('q', '').strip()
    platform = request.args.get('platform', '')
    page = request.args.get('page', 1, type=int)
    
    if not query and not platform:
        return redirect(url_for('portfolio'))
    
    # 검색 쿼리 구성
    video_query = Video.query
    
    if query:
        search_filter = db.or_(
            Video.title.contains(query),
            Video.description.contains(query),
            Video.author.contains(query),
            Video.tags.contains(query)
        )
        video_query = video_query.filter(search_filter)
    
    if platform:
        video_query = video_query.filter(Video.platform == platform)
    
    videos = video_query.order_by(Video.date_uploaded.desc()).paginate(
        page=page, per_page=9, error_out=False
    )
    
    return render_template('portfolio.html', 
                         videos=videos.items, 
                         pagination=videos,
                         search_query=query,
                         search_platform=platform)

@app.route('/portfolio/featured')
def featured_videos():
    """추천 영상 목록"""
    page = request.args.get('page', 1, type=int)
    videos = Video.query.filter_by(is_featured=True).order_by(
        Video.date_uploaded.desc()
    ).paginate(page=page, per_page=9, error_out=False)
    
    return render_template('portfolio.html', 
                         videos=videos.items, 
                         pagination=videos,
                         page_title="추천 영상")

# 관리자 페이지에 영상 통계 추가
@app.route('/admin/video_stats')
@admin_required
def admin_video_stats():
    """관리자용 영상 통계"""
    try:
        stats = {
            'total_videos': Video.query.count(),
            'youtube_videos': Video.query.filter_by(platform='youtube').count(),
            'vimeo_videos': Video.query.filter_by(platform='vimeo').count(),
            'local_videos': Video.query.filter_by(platform='local').count(),
            'total_views': db.session.query(db.func.sum(Video.view_count)).scalar() or 0,
            'total_likes': db.session.query(db.func.sum(Video.like_count)).scalar() or 0,
            'featured_count': Video.query.filter_by(is_featured=True).count()
        }
        
        recent_videos = Video.query.order_by(Video.date_uploaded.desc()).limit(5).all()
        popular_videos = Video.query.order_by(Video.view_count.desc()).limit(5).all()
        
        return render_template('admin_video_stats.html', 
                             stats=stats,
                             recent_videos=recent_videos,
                             popular_videos=popular_videos)
    except Exception as e:
        print(f"통계 조회 오류: {e}")
        flash('통계를 불러올 수 없습니다.')
        return redirect(url_for('admin'))

# YouTube URL 유효성 검사 API
@app.route('/api/validate_youtube_url', methods=['POST'])
@admin_required
def validate_youtube_url():
    """YouTube URL 유효성 검사"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        
        video_id = extract_youtube_video_id(url)
        if not video_id:
            return jsonify({'valid': False, 'message': '올바른 YouTube URL이 아닙니다.'})
        
        # 중복 확인
        existing = Video.query.filter_by(platform='youtube', video_id=video_id).first()
        if existing:
            return jsonify({'valid': False, 'message': '이미 등록된 영상입니다.'})
        
        # YouTube 정보 가져오기
        video_info = get_youtube_video_info(video_id)
        if video_info:
            return jsonify({
                'valid': True,
                'video_id': video_id,
                'info': video_info
            })
        else:
            return jsonify({'valid': False, 'message': '영상 정보를 가져올 수 없습니다.'})
            
    except Exception as e:
        return jsonify({'valid': False, 'message': f'오류가 발생했습니다: {str(e)}'})

# Vimeo URL 유효성 검사 API
@app.route('/api/validate_vimeo_url', methods=['POST'])
@admin_required
def validate_vimeo_url():
    """Vimeo URL 유효성 검사"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        
        video_id = extract_vimeo_video_id(url)
        if not video_id:
            return jsonify({'valid': False, 'message': '올바른 Vimeo URL이 아닙니다.'})
        
        # 중복 확인
        existing = Video.query.filter_by(platform='vimeo', video_id=video_id).first()
        if existing:
            return jsonify({'valid': False, 'message': '이미 등록된 영상입니다.'})
        
        # Vimeo 정보 가져오기
        video_info = get_vimeo_video_info(video_id)
        if video_info:
            return jsonify({
                'valid': True,
                'video_id': video_id,
                'info': video_info
            })
        else:
            return jsonify({'valid': False, 'message': '영상 정보를 가져올 수 없습니다.'})
            
    except Exception as e:
        return jsonify({'valid': False, 'message': f'오류가 발생했습니다: {str(e)}'})

# 기존 resize_image 함수 수정 (이미 있다면 대체)
def resize_image(filepath, max_size=(640, 360)):
    """이미지 크기 조정"""
    try:
        from PIL import Image
        
        file_extension = os.path.splitext(filepath)[1].lower()
        if file_extension not in ['.jpg', '.jpeg', '.png', '.gif']:
            print(f"지원하지 않는 이미지 형식: {file_extension}")
            return
            
        with Image.open(filepath) as img:
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                if file_extension in ['.jpg', '.jpeg']:
                    img.save(filepath, 'JPEG', optimize=True, quality=85)
                elif file_extension == '.png':
                    img.save(filepath, 'PNG', optimize=True)
                else:
                    img.save(filepath, optimize=True, quality=85)
                    
                print(f"이미지 리사이징 완료: {filepath}")
            else:
                print(f"이미지 크기가 적절함: {filepath}")
                
    except Exception as e:
        print(f"이미지 리사이징 오류: {e}")

# base.html의 context_processor에 추가 (기존 것과 병합)
@app.context_processor
def inject_admin_status():
    return dict(
        is_admin=session.get('is_admin', False),
        get_display_date=get_display_date,
        extract_date_from_content=extract_date_from_content
    )

# 데이터베이스 테이블 생성
# 기존 데이터베이스가 있다면 다음 명령어로 새 테이블을 생성해야 합니다:
# with app.app_context():
#     db.create_all()

print("하이브리드 영상 포트폴리오 시스템이 설정되었습니다!")
print("지원 플랫폼: YouTube, Vimeo, 로컬 파일")
print("필요한 패키지: requests, Pillow")
print("데이터베이스 테이블 생성: db.create_all() 실행")

# 추가 유틸리티 함수들

def format_duration(seconds):
    """초를 MM:SS 또는 HH:MM:SS 형식으로 변환"""
    if not seconds:
        return None
    
    try:
        total_seconds = int(float(seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    except (ValueError, TypeError):
        return None

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
    """비디오 썸네일 URL을 안전하게 가져오는 함수"""
    if video.thumbnail_filename:
        # 로컬 썸네일이 있는 경우
        return url_for('static', filename=f'uploads/thumbnails/{video.thumbnail_filename}')
    elif video.platform == 'youtube' and video.video_id:
        # YouTube 썸네일 (여러 해상도 시도)
        return f"https://img.youtube.com/vi/{video.video_id}/maxresdefault.jpg"
    elif video.platform == 'vimeo' and video.video_id:
        # Vimeo 썸네일은 API 호출이 필요하므로 기본 이미지 사용
        return None
    else:
        return None
    
# 템플릿에서 사용할 수 있도록 컨텍스트에 추가
@app.context_processor
def inject_video_utils():
    return dict(
        get_video_embed_url=get_video_embed_url,
        get_video_thumbnail_url=get_video_thumbnail_url,
        format_duration=format_duration
    )


def get_valid_youtube_thumbnail(video_id):
    """유효한 YouTube 썸네일 URL을 찾아서 반환"""
    sizes = ['hqdefault', 'mqdefault', 'default']
    
    for size in sizes:
        url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        try:
            response = requests.head(url, timeout=5)
            if response.status_code == 200:
                return url
        except:
            continue
    
    return None

def update_youtube_thumbnails():
    """기존 YouTube 영상들의 유효한 썸네일 URL 업데이트"""
    youtube_videos = Video.query.filter_by(platform='youtube').all()
    
    for video in youtube_videos:
        if video.video_id:
            valid_thumbnail = get_valid_youtube_thumbnail(video.video_id)
            if valid_thumbnail:
                video.thumbnail_url = valid_thumbnail
                print(f"썸네일 업데이트: {video.title} -> {valid_thumbnail}")
    
    db.session.commit()
    return len(youtube_videos)


@app.route('/debug/thumbnails')
@admin_required
def debug_thumbnails():
    videos = Video.query.filter_by(platform='youtube').all()
    
    html = "<h1>YouTube 썸네일 디버그</h1>"
    
    for video in videos:
        html += f"""
        <div style="margin-bottom: 30px; padding: 20px; border: 1px solid #ddd;">
            <h3>{video.title}</h3>
            <p>Video ID: {video.video_id}</p>
            <p>저장된 썸네일 URL: {video.thumbnail_url}</p>
            
            <h4>썸네일 테스트:</h4>
            <img src="https://img.youtube.com/vi/{video.video_id}/hqdefault.jpg" 
                 style="width: 200px; height: auto; margin: 5px;"
                 alt="hqdefault">
            <img src="https://img.youtube.com/vi/{video.video_id}/mqdefault.jpg" 
                 style="width: 200px; height: auto; margin: 5px;"
                 alt="mqdefault">
            <img src="https://img.youtube.com/vi/{video.video_id}/default.jpg" 
                 style="width: 200px; height: auto; margin: 5px;"
                 alt="default">
        </div>
        """
    
    return html


# YouTube/Vimeo URL에서 ID 추출 함수들
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

# 영상 수정 페이지
@app.route('/edit_video/<int:video_id>', methods=['GET', 'POST'])
@admin_required
def edit_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    if request.method == 'POST':
        try:
            # 기본 정보 업데이트
            video.title = request.form.get('title', '').strip()
            video.description = request.form.get('description', '').strip()
            video.author = request.form.get('author', '앙상블 다울').strip()
            
            # URL이 변경된 경우 처리
            new_url = request.form.get('video_url', '').strip()
            if new_url and new_url != video.external_url:
                if video.platform == 'youtube':
                    new_video_id = extract_youtube_video_id(new_url)
                    if new_video_id:
                        video.video_id = new_video_id
                        video.external_url = new_url
                    else:
                        flash('올바른 YouTube URL을 입력해주세요.')
                        return redirect(request.url)
                        
                elif video.platform == 'vimeo':
                    new_video_id = extract_vimeo_video_id(new_url)
                    if new_video_id:
                        video.video_id = new_video_id
                        video.external_url = new_url
                    else:
                        flash('올바른 Vimeo URL을 입력해주세요.')
                        return redirect(request.url)
            
            # 태그 처리 (있는 경우)
            if hasattr(video, 'tags'):
                video.tags = request.form.get('tags', '').strip()
            
            # 공연 날짜 처리 (있는 경우)
            if hasattr(video, 'performance_date'):
                performance_date_str = request.form.get('performance_date')
                if performance_date_str:
                    try:
                        video.performance_date = datetime.strptime(performance_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        video.performance_date = None
                else:
                    video.performance_date = None
            
            # 썸네일 업로드 처리 (있는 경우)
            if 'thumbnail' in request.files and hasattr(video, 'thumbnail_filename'):
                thumbnail_file = request.files['thumbnail']
                if thumbnail_file and thumbnail_file.filename != '' and allowed_file(thumbnail_file.filename):
                    # 기존 썸네일 삭제
                    if video.thumbnail_filename:
                        old_thumbnail_path = os.path.join(app.config.get('THUMBNAIL_UPLOAD_FOLDER', ''), video.thumbnail_filename)
                        if os.path.exists(old_thumbnail_path):
                            os.remove(old_thumbnail_path)
                    
                    # 새 썸네일 저장
                    filename = secure_filename(thumbnail_file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"thumb_{timestamp}_{filename}"
                    
                    # 썸네일 폴더가 없으면 생성
                    thumbnail_folder = app.config.get('THUMBNAIL_UPLOAD_FOLDER', os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails'))
                    os.makedirs(thumbnail_folder, exist_ok=True)
                    
                    filepath = os.path.join(thumbnail_folder, filename)
                    thumbnail_file.save(filepath)
                    video.thumbnail_filename = filename
                    video.thumbnail_url = None  # 로컬 파일 사용 시 외부 URL 제거
            
            db.session.commit()
            flash('영상 정보가 성공적으로 수정되었습니다!')
            return redirect(url_for('view_video', video_id=video.id))
            
        except Exception as e:
            print(f"영상 수정 오류: {e}")
            flash('영상 수정 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('edit_video.html', video=video)

# 영상 삭제
@app.route('/delete_video/<int:video_id>', methods=['POST'])
@admin_required
def delete_video(video_id):
    try:
        video = Video.query.get_or_404(video_id)
        video_title = video.title
        
        # 로컬 파일들 삭제
        if hasattr(video, 'video_filename') and video.video_filename:
            video_path = os.path.join(app.config.get('LOCAL_VIDEO_FOLDER', ''), video.video_filename)
            if os.path.exists(video_path):
                os.remove(video_path)
        
        if hasattr(video, 'thumbnail_filename') and video.thumbnail_filename:
            thumbnail_path = os.path.join(app.config.get('THUMBNAIL_UPLOAD_FOLDER', ''), video.thumbnail_filename)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        
        # 데이터베이스에서 삭제
        db.session.delete(video)
        db.session.commit()
        
        flash(f'영상 "{video_title}"이 성공적으로 삭제되었습니다!')
        
    except Exception as e:
        print(f"영상 삭제 오류: {e}")
        flash('영상 삭제 중 오류가 발생했습니다.')
    
    return redirect(url_for('portfolio'))

# 영상 상세보기 (조회수 증가 포함)
@app.route('/video/<int:video_id>')
def view_video(video_id):
    try:
        video = Video.query.get_or_404(video_id)
        
        # 조회수 증가
        video.view_count = (video.view_count or 0) + 1
        db.session.commit()
        
        # 관련 영상 가져오기 (선택사항)
        related_videos = []
        if hasattr(video, 'tags') and video.tags:
            # 같은 태그를 가진 영상들
            related_videos = Video.query.filter(
                Video.id != video.id,
                Video.tags.contains(video.tags.split(',')[0])
            ).limit(4).all()
        
        if len(related_videos) < 4:
            # 부족하면 최신 영상으로 채움
            additional_videos = Video.query.filter(
                Video.id != video.id
            ).order_by(Video.date_uploaded.desc()).limit(4 - len(related_videos)).all()
            related_videos.extend(additional_videos)
        
        return render_template('video_detail.html', video=video, related_videos=related_videos)
        
    except Exception as e:
        print(f"영상 조회 오류: {e}")
        flash('영상을 불러올 수 없습니다.')
        return redirect(url_for('portfolio'))

# 영상 추가 (기존 개선)
@app.route('/add_video', methods=['GET', 'POST'])
@admin_required
def add_video():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            author = request.form.get('author', '앙상블 다울').strip()
            platform = request.form.get('platform', 'youtube')
            video_url = request.form.get('video_url', '').strip()
            
            if not title:
                flash('영상 제목을 입력해주세요.')
                return redirect(request.url)
            
            if not video_url:
                flash('영상 URL을 입력해주세요.')
                return redirect(request.url)
            
            # URL에서 video_id 추출
            video_id = None
            if platform == 'youtube':
                video_id = extract_youtube_video_id(video_url)
                if not video_id:
                    flash('올바른 YouTube URL을 입력해주세요.')
                    return redirect(request.url)
                    
                # 중복 확인
                existing = Video.query.filter_by(platform='youtube', video_id=video_id).first()
                if existing:
                    flash('이미 등록된 YouTube 영상입니다.')
                    return redirect(request.url)
                    
            elif platform == 'vimeo':
                video_id = extract_vimeo_video_id(video_url)
                if not video_id:
                    flash('올바른 Vimeo URL을 입력해주세요.')
                    return redirect(request.url)
                    
                # 중복 확인
                existing = Video.query.filter_by(platform='vimeo', video_id=video_id).first()
                if existing:
                    flash('이미 등록된 Vimeo 영상입니다.')
                    return redirect(request.url)
            
            # 새 영상 객체 생성
            video = Video(
                title=title,
                description=description,
                author=author,
                platform=platform,
                video_id=video_id,
                external_url=video_url
            )
            
            # 선택적 필드들 (테이블에 있는 경우에만)
            if hasattr(video, 'tags'):
                video.tags = request.form.get('tags', '').strip()
            
            if hasattr(video, 'performance_date'):
                performance_date_str = request.form.get('performance_date')
                if performance_date_str:
                    try:
                        video.performance_date = datetime.strptime(performance_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
            
            db.session.add(video)
            db.session.commit()
            
            flash('영상이 성공적으로 추가되었습니다!')
            return redirect(url_for('portfolio'))
            
        except Exception as e:
            print(f"영상 추가 오류: {e}")
            flash('영상 추가 중 오류가 발생했습니다.')
            return redirect(request.url)
    
    return render_template('add_video.html')

@app.route('/portfolio')
def portfolio():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 9
        
        # 기본 쿼리
        query = Video.query.order_by(Video.date_uploaded.desc())
        
        # 페이지네이션
        videos_paginated = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # 각 비디오의 본문에서 날짜 추출하고 +1일 처리
        for video in videos_paginated.items:
            if video.description:
                # 본문에서 YYYY.M.D 또는 YYYY.MM.DD 형식의 날짜 찾기
                date_match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', video.description)
                if date_match:
                    try:
                        # 찾은 날짜를 파싱하고 +1일 추가
                        year = int(date_match.group(1))
                        month = int(date_match.group(2))
                        day = int(date_match.group(3))
                        
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
        print(f"포트폴리오 오류: {e}")
        flash('포트폴리오를 불러오는 중 문제가 발생했습니다.')
        return render_template('portfolio.html', videos=[], pagination=None)
    

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 데이터베이스 테이블 생성
    app.run(debug=True)