from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import *
from users.models import UserProfile
from .forms import DocumentForm, VideoLessonForm, TestFileUploadForm, SubjectForm, TestCreateForm
import matplotlib.pyplot as plt
import io
import base64
import numpy as np
import matplotlib

matplotlib.use('Agg')
from django.conf import settings
from .utils import update_user_difficulty_level  # Bu yerda import qilamiz
from matplotlib.patches import Patch
import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
import logging
from django.utils import translation


def home(request):
    """Bosh sahifa - Yangilangan versiya"""
    graphic = None

    # BARCHA foydalanuvchilar uchun materiallar
    videos = VideoLesson.objects.all()
    documents = Document.objects.all()
    tests = Test.objects.all()
    users = UserProfile.objects.all()

    # Fanlar bo'yicha materiallar statistikasi
    subject_materials = {}

    # 1. Har bir fan uchun materiallarni hisoblash
    for doc in documents:
        if doc.subject:
            subject_name = doc.subject.name
            if subject_name not in subject_materials:
                subject_materials[subject_name] = {
                    'documents': 1,
                    'videos': 0,
                    'tests': 0,
                    'total': 1
                }
            else:
                subject_materials[subject_name]['documents'] += 1
                subject_materials[subject_name]['total'] += 1

    for video in videos:
        if video.subject:
            subject_name = video.subject.name
            if subject_name not in subject_materials:
                subject_materials[subject_name] = {
                    'documents': 0,
                    'videos': 1,
                    'tests': 0,
                    'total': 1
                }
            else:
                subject_materials[subject_name]['videos'] += 1
                subject_materials[subject_name]['total'] += 1

    for test in tests:
        if test.subject:
            subject_name = test.subject.name
            if subject_name not in subject_materials:
                subject_materials[subject_name] = {
                    'documents': 0,
                    'videos': 0,
                    'tests': 1,
                    'total': 1
                }
            else:
                subject_materials[subject_name]['tests'] += 1
                subject_materials[subject_name]['total'] += 1

    # 2. Foydalanuvchilarning har bir fan uchun o'zlashtirish darajasi
    user_subject_progress = {}
    if request.user.is_authenticated:
        test_results = TestResult.objects.filter(user=request.user).select_related('test')

        for result in test_results:
            if result.test and result.test.subject:
                subject_name = result.test.subject.name
                percentage = result.percentage()

                if subject_name not in user_subject_progress:
                    user_subject_progress[subject_name] = {
                        'total_percentage': percentage,
                        'count': 1,
                        'avg_percentage': percentage
                    }
                else:
                    user_subject_progress[subject_name]['total_percentage'] += percentage
                    user_subject_progress[subject_name]['count'] += 1
                    user_subject_progress[subject_name]['avg_percentage'] = \
                        user_subject_progress[subject_name]['total_percentage'] / \
                        user_subject_progress[subject_name]['count']

    # 3. Grafik yaratish - IKKALA DIAGRAMMA HAM DUMALOQ
    if subject_materials:

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

        # 3.1. Fanlar bo'yicha materiallar (dumaloq diagramma)
        subjects = list(subject_materials.keys())
        total_materials = [subject_materials[subj]['total'] for subj in subjects]

        # Materiallar soni bo'yicha tartiblash
        sorted_indices = np.argsort(total_materials)[::-1]
        subjects = [subjects[i] for i in sorted_indices]
        total_materials = [total_materials[i] for i in sorted_indices]

        # Faqat materiali ko'p bo'lgan 10 ta fanni ko'rsatish
        if len(subjects) > 10:
            subjects = subjects[:10]
            total_materials = total_materials[:10]
            others_total = sum(total_materials[10:]) if len(total_materials) > 10 else 0
            subjects.append('Boshqa fanlar')
            total_materials.append(others_total)

        colors1 = plt.cm.Set3(np.linspace(0, 1, len(subjects)))
        wedges1, texts1, autotexts1 = ax1.pie(
            total_materials,
            labels=subjects,
            colors=colors1,
            autopct=lambda pct: f'{pct:.1f}%\n({int(pct * sum(total_materials) / 100)})' if pct > 5 else '',
            startangle=90,
            pctdistance=0.8,
            textprops={'fontsize': 9}
        )
        ax1.set_title('Fanlar bo\'yicha materiallar taqsimoti', fontweight='bold', fontsize=12, pad=20)

        # Markazda ma'lumot
        centre_circle1 = plt.Circle((0, 0), 0.70, fc='white')
        ax1.add_artist(centre_circle1)
        total_all_materials = sum(total_materials)
        ax1.text(0, 0.1, f'Jami:', ha='center', va='center', fontsize=10, fontweight='bold')
        ax1.text(0, -0.05, f'{total_all_materials}', ha='center', va='center', fontsize=16, fontweight='bold')
        ax1.text(0, -0.15, f'material', ha='center', va='center', fontsize=9)

        # 3.2. Foydalanuvchilarning o'zlashtirish darajasi (dumaloq diagramma)
        if user_subject_progress and request.user.is_authenticated:
            user_subjects = list(user_subject_progress.keys())
            user_avg_percentages = [user_subject_progress[subj]['avg_percentage'] for subj in user_subjects]

            if len(user_subjects) > 0:
                # O'zlashtirish darajasi bo'yicha tartiblash
                sorted_indices = np.argsort(user_avg_percentages)[::-1]
                user_subjects = [user_subjects[i] for i in sorted_indices]
                user_avg_percentages = [user_avg_percentages[i] for i in sorted_indices]

                # Faqat 10 ta fan ko'rsatish
                if len(user_subjects) > 10:
                    user_subjects = user_subjects[:10]
                    user_avg_percentages = user_avg_percentages[:10]

                # Baholash bo'yicha ranglar
                colors2 = []
                for perc in user_avg_percentages:
                    if perc >= 80:
                        colors2.append('#4CAF50')  # Yaxshi
                    elif perc >= 60:
                        colors2.append('#FFC107')  # O'rtacha
                    else:
                        colors2.append('#F44336')  # Qoniqarsiz

                wedges2, texts2, autotexts2 = ax2.pie(
                    user_avg_percentages,
                    labels=user_subjects,
                    colors=colors2,
                    autopct=lambda pct: f'{pct:.1f}%' if pct > 5 else '',
                    startangle=90,
                    pctdistance=0.8,
                    textprops={'fontsize': 9}
                )

                # Markazda ma'lumot
                centre_circle2 = plt.Circle((0, 0), 0.70, fc='white')
                ax2.add_artist(centre_circle2)
                avg_overall = sum(user_avg_percentages) / len(user_avg_percentages) if user_avg_percentages else 0
                ax2.text(0, 0.1, f'O\'rtacha:', ha='center', va='center', fontsize=10, fontweight='bold')
                ax2.text(0, -0.05, f'{avg_overall:.1f}%', ha='center', va='center', fontsize=16, fontweight='bold')
                ax2.text(0, -0.15, f'{len(user_subjects)} fan', ha='center', va='center', fontsize=9)

                # Legend
                legend_elements = [
                    Patch(facecolor='#4CAF50', label='Yaxshi (80-100%)'),
                    Patch(facecolor='#FFC107', label='O\'rtacha (60-79%)'),
                    Patch(facecolor='#F44336', label='Qoniqarsiz (0-59%)')
                ]
                ax2.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)

            else:
                ax2.text(0.5, 0.5, 'Hozircha test\nnatijalari yo\'q',
                         ha='center', va='center', fontsize=12,
                         transform=ax2.transAxes)
        else:
            ax2.text(0.5, 0.5, 'Tizimga kiring\nva test topshiring',
                     ha='center', va='center', fontsize=12,
                     transform=ax2.transAxes)

        ax2.set_title(f'{"Foydalanuvchi" if request.user.is_authenticated else "Umumiy"} o\'zlashtirish darajasi',
                      fontweight='bold', fontsize=12, pad=20)

        plt.suptitle('Fanlar statistikasi', fontsize=14, fontweight='bold', y=0.95)
        plt.tight_layout()

        # Grafikni base64 ga o'tkazish
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_png = buffer.getvalue()
        buffer.close()
        graphic = base64.b64encode(image_png).decode('utf-8')
        plt.close()

    return render(request, 'app1/home.html', {
        'graphic': graphic,
        'videos': videos,
        'videos_count': videos.count(),
        'documents': documents,
        'documents_count': documents.count(),
        'test_count': tests.count(),
        'user_count': users.count(),
        'subject_materials': subject_materials,
        'user_subject_progress': user_subject_progress if request.user.is_authenticated else None,
        'total_subjects': len(subject_materials),
        'avg_progress': sum([data['avg_percentage'] for data in user_subject_progress.values()]) / len(
            user_subject_progress)
        if user_subject_progress else 0
    })


def about(request):
    """Loyiha haqida sahifa"""
    return render(request, 'app1/about.html')


def documents(request):
    """Hujjatlar ro'yxati"""
    subjects = Subject.objects.prefetch_related('document_set').all()
    return render(request, 'app1/documents.html', {'subjects': subjects})


# views.py ga qo'shamiz
def subject_documents(request, subject_id):
    """Fanga oid hujjatlar ro'yxati"""
    subject = get_object_or_404(Subject, id=subject_id)
    documents = Document.objects.filter(subject=subject).order_by('-uploaded_at')

    return render(request, 'app1/subject_documents.html', {
        'subject': subject,
        'documents': documents
    })


# views.py dagi add_document funksiyasini yangilaymiz
@login_required
def add_document(request):
    """Hujjat qo'shish (faqat admin)"""
    if not request.user.is_staff:
        return redirect('home')

    # URL dan fan ID sini olish
    subject_id = request.GET.get('subject')

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Material muvaffaqiyatli qo‘shildi!')
            return redirect('documents')
    else:
        initial = {}
        if subject_id:
            try:
                subject = Subject.objects.get(id=subject_id)
                initial['subject'] = subject
            except Subject.DoesNotExist:
                pass
        form = DocumentForm(initial=initial)

    return render(request, 'app1/add_document.html', {'form': form})


def video_lessons(request):
    """Video darslar ro'yxati"""
    videos = VideoLesson.objects.all()
    videos_count = videos.count()  # Sonini hisoblash

    return render(request, 'app1/video_lessons.html', {'videos': videos})


@login_required
def add_video(request):
    """Video qo'shish"""
    if request.method == 'POST':
        form = VideoLessonForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Video muvaffaqiyatli qo‘shildi!')
            return redirect('video_lessons')
    else:
        form = VideoLessonForm()
    return render(request, 'app1/add_video.html', {'form': form})


# -------------------- AI YORDAMCHI --------------------
# views.py - CSRF va localization bilan ishlaydigan versiya


logger = logging.getLogger(__name__)


@csrf_exempt  # CSRF dan ozod qilish
def ai_chat(request):
    """AI chatbot - localization bilan ishlaydi"""

    # 🔑 Joriy tilni olish
    lang = translation.get_language()  # 'uz', 'ru', 'en'

    if request.method == 'POST':
        try:
            # JSON ma'lumotlarni olish
            if request.content_type == 'application/json':
                data = json.loads(request.body.decode('utf-8'))
            else:
                data = request.POST

            user_message = data.get('message', '').strip()

            if not user_message:
                return JsonResponse({
                    'success': False,
                    'response': 'Xabar matni kiritilmagan',
                    'type': 'error'
                })

            print(f"📩 Foydalanuvchi xabari: {user_message}")
            print(f"🌍 Joriy til: {lang}")

            api_key = settings.GROQ_API_KEY

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {
                        "role": "system",
                        "content": f"""
                            Siz foydali IT va dasturlash yordamchisisiz.
                            Javoblaringiz aniq, tushunarli va amaliy bo'lsin.

                            Javob tili: {lang}
                            Faqat shu tilda javob bering.

                            Agar kod namunalari kerak bo'lsa, to'liq va izohli kod yozing.
                            Murojaat qilishda "siz" deb murojaat qiling.
                            """
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            print(f"🔧 API Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                ai_response = result['choices'][0]['message']['content']

                print(f"✅ AI javobi: {ai_response[:100]}...")

                return JsonResponse({
                    'success': True,
                    'response': ai_response,
                    'type': 'ai'
                })

            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                print(f"❌ API xatosi: {response.status_code}")

                return JsonResponse({
                    'success': True,
                    'response': "Server vaqtincha javob bermayapti.",
                    'type': 'offline'
                })

        except Exception as e:
            logger.exception("🔥 AI chat xatosi")
            return JsonResponse({
                'success': False,
                'response': f"Xatolik yuz berdi: {str(e)}",
                'type': 'error'
            })

    # GET so'rovi (sahifa ochilganda)
    print("📄 GET so'rovi keldi, HTML sahifa yuborilmoqda...")
    return render(request, 'app1/ai_chat.html')


def tests(request):
    subjects = Subject.objects.prefetch_related('test_set').all()

    themed_tests = Test.objects.filter(
        subject__isnull=True,
        is_active=True
    )
    son = themed_tests.count()
    return render(request, 'app1/tests.html', {
        'subjects': subjects,
        'themed_tests': themed_tests,
    })


@login_required
def delete_test(request, test_id):
    """Testni o'chirish"""
    if not request.user.is_staff:
        messages.error(request, "Ruxsat yo'q!")
        return redirect('test_list')

    test = get_object_or_404(Test, id=test_id)
    test_title = test.title

    if request.method == 'POST':
        test.delete()
        messages.success(request, f'"{test_title}" testi o\'chirildi!')

    return redirect('tests')


# views.py dagi take_test funksiyasida
@login_required
def take_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if not test.is_available():
        messages.error(request, "Bu test hozir faol emas")
        return redirect('tests')

    # Foydalanuvchi uchun mos savollarni olish
    questions = test.get_questions_for_user(request.user)
    total_questions = len(questions)

    if request.method == 'POST':
        # JavaScript dan kelgan sarflangan vaqt
        time_taken_str = request.POST.get('time_taken', '0')

        try:
            time_taken_seconds = int(time_taken_str)
        except (ValueError, TypeError):
            time_taken_seconds = 0

        # Vaqt chegarasini tekshirish
        max_time_seconds = test.time_limit_minutes * 60

        if time_taken_seconds > max_time_seconds:
            messages.warning(request, "Test vaqti tugadi!")
            time_taken_seconds = max_time_seconds

        score = 0
        total_questions = len(questions)

        # Javoblarni tekshirish
        for question in questions:
            user_answer_id = request.POST.get(f'question_{question.id}')
            if user_answer_id:
                try:
                    user_answer = Answer.objects.get(id=int(user_answer_id), question=question)
                    if user_answer.is_correct:
                        score += 1
                except (ValueError, Answer.DoesNotExist):
                    pass

        # Natijani saqlash
        test_result = TestResult.objects.create(
            user=request.user,
            test=test,
            score=score,
            total_questions=total_questions,
            time_taken_seconds=time_taken_seconds
        )

        # O'rtacha qiyinlik darajasini hisoblash
        test_result.calculate_average_difficulty(questions)

        # Foydalanuvchi darajasini yangilash
        update_user_difficulty_level(request.user, test.subject, test_result)

        return render(request, 'app1/test_result.html', {
            'test': test,
            'score': score,
            'total_questions': total_questions,
            'percentage': (score / total_questions) * 100 if total_questions > 0 else 0,
            'time_taken_seconds': time_taken_seconds,
            'average_difficulty': test_result.average_difficulty
        })

    return render(request, 'app1/take_test.html', {
        'test': test,
        'questions': questions,
        'time_limit_seconds': test.time_limit_minutes * 60,
        'total_questions': total_questions
    })


@login_required
def submit_test(request, test_id):
    """Testni yakunlash (eski versiya)"""
    if request.method == 'POST':
        test = get_object_or_404(Test, id=test_id)
        questions = Question.objects.filter(test=test)
        score = 0

        for question in questions:
            selected_answer_id = request.POST.get(f'question_{question.id}')
            if selected_answer_id:
                selected_answer = Answer.objects.get(id=selected_answer_id)
                if selected_answer.is_correct:
                    score += 1

        TestResult.objects.create(
            user=request.user,
            test=test,
            score=score,
            total_questions=questions.count()
        )

        return render(request, 'app1/test_result.html', {
            'test': test,
            'score': score,
            'total': questions.count()
        })


# views.py - test_results funksiyasini yangilang
@login_required
def test_results(request):
    """Foydalanuvchi test natijalari"""
    results = TestResult.objects.filter(user=request.user).select_related('test').order_by('-completed_at')

    # Debug ma'lumotlari
    print(f"Foydalanuvchi: {request.user.username}")
    print(f"Natijalar soni: {results.count()}")

    # O'rtacha foizni hisoblaymiz
    average_percentage = 0
    if results:
        total_percentage = sum(result.percentage() for result in results)
        average_percentage = round(total_percentage / results.count(), 1)
        print(f"O'rtacha foiz: {average_percentage}%")

    return render(request, 'app1/test_results.html', {
        'results': results,
        'average_percentage': average_percentage
    })


@login_required
def test_detail(request, test_id):
    """Test tafsilotlari"""
    test = get_object_or_404(Test, id=test_id)
    return render(request, 'app1/test_detail.html', {
        'test': test,
        'status': test.get_status(),
        'is_available': test.is_available()
    })


def test_status_api(request, test_id):
    """Test holati API"""
    test = get_object_or_404(Test, id=test_id)
    data = {
        'status': test.get_status(),
        'is_available': test.is_available(),
        'time_until_start': test.time_until_start().total_seconds() if test.time_until_start() else None,
        'time_remaining': test.time_remaining().total_seconds() if test.time_remaining() else None,
        'time_limit_minutes': test.time_limit_minutes,
    }
    return JsonResponse(data)


# -------------------- ADMIN FUNKSIYALARI --------------------

def is_admin(user):
    """Admin tekshiruvi"""
    return user.is_staff


@login_required
@user_passes_test(is_admin)
def add_subject(request):
    """Yangi fan qo'shish"""
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f'"{subject.name}" fani muvaffaqiyatli qo\'shildi!')
            return redirect('tests')
    else:
        form = SubjectForm()
    return render(request, 'app1/add_subject.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def upload_test_file(request):
    """Test fayl yuklash"""
    if request.method == 'POST':
        form = TestFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            test_file = form.save()
            success, message = test_file.process_test_file()
            if success:
                messages.success(request, f"Test muvaffaqiyatli yuklandi! {message}")
            else:
                messages.warning(request, f"Fayl yuklandi, lekin xatolik: {message}")
            return redirect('tests')
    else:
        form = TestFileUploadForm()
    return render(request, 'app1/upload_test_file.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def create_test(request):
    """Qo'lda test yaratish"""
    if request.method == 'POST':
        form = TestCreateForm(request.POST)
        if form.is_valid():
            test = form.save()
            messages.success(request, f"Test '{test.title}' muvaffaqiyatli yaratildi")
            return redirect('tests')
    else:
        form = TestCreateForm()
    return render(request, 'app1/upload_test_file.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def admin_stats(request):
    """Admin statistikasi"""
    users = User.objects.all()
    return render(request, 'app1/admin_stats.html', {'users': users})


@login_required
@user_passes_test(is_admin)
def user_stats(request, user_id):
    """Foydalanuvchi statistikasi - Fanlar bo'yicha maksimal natijalar bilan Dumaloq diagramma"""
    user = get_object_or_404(User, id=user_id)
    test_results = TestResult.objects.filter(user=user).select_related('test').order_by('completed_at')

    # Fanlar bo'yicha guruhlash va har bir fanda eng yaxshi natijani olish
    subject_stats = {}
    for result in test_results:
        subject_name = result.test.subject.name if result.test.subject else "Noma'lum fan"
        percentage = result.percentage()

        # Har bir fan uchun eng yaxshi natijani saqlash
        if subject_name not in subject_stats or percentage > subject_stats[subject_name]['best_score']:
            subject_stats[subject_name] = {
                'best_score': percentage,
                'test_count': subject_stats.get(subject_name, {}).get('test_count', 0) + 1,
                'last_test': result.completed_at
            }

    # Eng yaxshi umumiy natijani hisoblash
    best_percentage = 0
    if test_results:
        percentages = [result.percentage() for result in test_results]
        best_percentage = max(percentages)

    # Dumaloq diagramma yaratish
    plt.figure(figsize=(10, 10))

    if subject_stats:
        # Fanlar va eng yaxshi ballar
        subjects = list(subject_stats.keys())
        best_scores = [subject_stats[subj]['best_score'] for subj in subjects]
        test_counts = [subject_stats[subj]['test_count'] for subj in subjects]

        # Ranglar
        colors = plt.cm.Set3(np.linspace(0, 1, len(subjects)))

        # Dumaloq diagramma
        wedges, texts, autotexts = plt.pie(
            best_scores,
            labels=subjects,
            colors=colors,
            autopct='%1.1f%%',
            startangle=90,
            pctdistance=0.85,
            textprops={'fontsize': 11}
        )

        # Markazda ma'lumot
        centre_circle = plt.Circle((0, 0), 0.70, fc='white')
        plt.gca().add_artist(centre_circle)

        # Markazda umumiy ma'lumot
        total_subjects = len(subjects)
        total_tests = sum(test_counts)
        avg_best_score = sum(best_scores) / len(best_scores) if best_scores else 0

        plt.text(0, 0.1, f'{user.username}', ha='center', va='center',
                 fontsize=16, fontweight='bold')
        plt.text(0, -0.05, f'Fanlar: {total_subjects}', ha='center', va='center',
                 fontsize=12)
        plt.text(0, -0.15, f'Testlar: {total_tests}', ha='center', va='center',
                 fontsize=12)
        plt.text(0, -0.25, f"O'rtacha: {avg_best_score:.1f}%", ha='center', va='center',
                 fontsize=12)

        # Sarlavha
        plt.title(f'{user.username} - Fanlar bo\'yicha Eng Yaxshi Natijalar',
                  fontsize=16, fontweight='bold', pad=20)

        # Legend - har bir fan uchun testlar soni va eng yaxshi ball
        legend_labels = []
        for i, (subject, stats) in enumerate(subject_stats.items()):
            legend_labels.append(f"{subject}: {stats['best_score']:.1f}% ({stats['test_count']} test)")

        plt.legend(wedges, legend_labels, title="Fanlar tafsiloti",
                   loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize=10)

        plt.tight_layout()

        # Grafikni base64 ga o'tkazish
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_png = buffer.getvalue()
        buffer.close()
        graphic = base64.b64encode(image_png).decode('utf-8')
        plt.close()
    else:
        graphic = None

    # Template uchun qo'shimcha ma'lumotlar
    subject_details = []
    if subject_stats:
        for subject, stats in subject_stats.items():
            subject_details.append({
                'name': subject,
                'best_score': stats['best_score'],
                'test_count': stats['test_count'],
                'last_test': stats['last_test'].strftime("%d.%m.%Y %H:%M") if stats['last_test'] else "Noma'lum"
            })
        # Eng yaxshi natija bo'yicha tartiblash
        subject_details.sort(key=lambda x: x['best_score'], reverse=True)

    return render(request, 'app1/user_stats.html', {
        'user': user,
        'test_results': test_results,
        'graphic': graphic,
        'best_percentage': round(best_percentage, 1),
        'subject_details': subject_details,  # Fanlar tafsiloti
        'total_subjects': len(subject_stats) if subject_stats else 0,
        'total_tests': sum([s['test_count'] for s in subject_stats.values()]) if subject_stats else 0,
        'avg_best_score': sum([s['best_score'] for s in subject_stats.values()]) / len(
            subject_stats) if subject_stats else 0
    })


@login_required
@user_passes_test(is_admin)
def user_profile_detail(request, user_id):
    """Foydalanuvchi profiling batafsil"""
    user = get_object_or_404(User, id=user_id)

    # Xavsiz usul bilan userprofile ni olish
    user_profile = getattr(user, 'userprofile', None)

    test_results = TestResult.objects.filter(user=user).select_related('test')

    return render(request, 'app1/user_profile_detail.html', {
        'profile_user': user,
        'user_profile': user_profile,
        'test_results': test_results
    })