from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
import json
from django.conf import settings
from django.views.decorators.http import require_POST
from .models import AITest, TestAttempt
from .forms import SimpleAITestForm
from groq import Groq


# app3/views.py - home funksiyasini yangilaymiz

def home(request):
    ai_tests = AITest.objects.filter(is_active=True).order_by('-created_at')

    for test in ai_tests:
        test.user_attempt = None

    if request.user.is_authenticated:
        attempts = TestAttempt.objects.filter(
            user=request.user,
            ai_test__in=ai_tests
        )
        attempts_map = {a.ai_test_id: a for a in attempts}

        for test in ai_tests:
            test.user_attempt = attempts_map.get(test.id)

    total_questions = sum(len(test.questions_data) for test in ai_tests)

    user_results_count = (
        TestAttempt.objects.filter(user=request.user).count()
        if request.user.is_authenticated else 0
    )

    return render(request, 'app3/home.html', {
        'ai_tests': ai_tests,
        'total_questions': total_questions,
        'user_results_count': user_results_count,
    })

# app3/views.py - admin_ai_chat funksiyasini to'g'rilaymiz
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_ai_chat(request):
    """Admin uchun AI chat bot test yaratish"""
    api_key_configured = hasattr(settings, 'GROQ_API_KEY') and settings.GROQ_API_KEY

    if request.method == 'POST':
        form = SimpleAITestForm(request.POST)
        if form.is_valid():
            topic = form.cleaned_data['topic']
            prompt_text = form.cleaned_data[
                              'prompt'] or f"{topic} haqida 10 ta test savoli tuzing. Har bir savolga 4 ta variant bering."

            # API kalit borligini tekshirish
            if not api_key_configured:
                messages.error(request, "❌ Groq API kaliti topilmadi. settings.py fayliga GROQ_API_KEY qo'shing")
                return redirect('app3:admin_ai_chat')

            try:

                # Groq API ga so'rov
                client = Groq(api_key=settings.GROQ_API_KEY)

                # MUHIM: Groq'ning response_format=json_object rejimi modeldan
                # albatta JSON OBYEKT ({..}) qaytarishni talab qiladi, JSON MASSIV
                # ([..]) emas. Shuning uchun savollarni "questions" kaliti ichida
                # so'raymiz, keyin pastda uni qayta massivga aylantiramiz.
                full_prompt = f"""
                {prompt_text}

                Iltimos, faqat quyidagi JSON formatida javob bering:
                {{
                  "questions": [
                    {{
                      "question": "Savol matni",
                      "options": ["A variant", "B variant", "C variant", "D variant"],
                      "correct": 0
                    }}
                  ]
                }}

                Savollar soni: 10 ta
                """

                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role": "system",
                            "content": "Siz test savollari yaratuvchi yordamchisiz. Faqat so'ralgan JSON formatida javob bering."
                        },
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )

                raw_response = response.choices[0].message.content

                # Modeldan kelgan {"questions": [...]} obyektini
                # create_test_from_ai_response() kutgan [...] massiv shakliga
                # qaytarib o'giramiz.
                try:
                    parsed = json.loads(raw_response)
                    questions_list = parsed.get("questions", []) if isinstance(parsed, dict) else parsed
                except (json.JSONDecodeError, AttributeError):
                    questions_list = []

                ai_response = json.dumps(questions_list, ensure_ascii=False)

                if not questions_list:
                    logger_msg = raw_response[:300] if raw_response else "(bo'sh javob)"
                    messages.error(
                        request,
                        f"❌ AI'dan savollar formatini ajratib bo'lmadi. Qayta urinib ko'ring. "
                        f"(Xom javob: {logger_msg})"
                    )
                    return redirect('app3:admin_ai_chat')

                # Test yaratish
                ai_test = AITest.objects.create(
                    topic=topic,
                    prompt=prompt_text,
                    ai_response=ai_response,
                    created_by=request.user
                )

                # Savollarni tizimga yuklash
                success, message = ai_test.create_test_from_ai_response()

                if success:
                    messages.success(request, f"✅ '{topic}' testi muvaffaqiyatli yaratildi! {message}")
                else:
                    messages.warning(request, f"⚠️ Test yaratildi, lekin: {message}")

                # Yangilangan testlar ro'yxati bilan redirect
                return redirect('app3:admin_ai_chat')

            except Exception as e:
                error_str = str(e)
                if "invalid_api_key" in error_str.lower() or "401" in error_str:
                    messages.error(request, "❌ Groq API kaliti noto'g'ri yoki mavjud emas")
                else:
                    messages.error(request, f"❌ Xatolik: {error_str}")
                return redirect('app3:admin_ai_chat')
    else:
        form = SimpleAITestForm()

    # So'nggi yaratilgan testlar
    ai_tests = AITest.objects.filter(created_by=request.user).order_by('-created_at')[:10]

    return render(request, 'app3/admin_ai_chat.html', {
        'form': form,
        'ai_tests': ai_tests,
        'api_key_configured': api_key_configured
    })



def take_test(request, test_id):
    """Testni ishlash"""
    ai_test = get_object_or_404(AITest, id=test_id, is_active=True)

    if request.method == 'POST':
        if request.user.is_authenticated:
            # Foydalanuvchi javoblarini hisoblash
            score = 0
            questions_data = ai_test.questions_data

            for i, q_data in enumerate(questions_data):
                user_answer = request.POST.get(f'question_{i}')
                if user_answer:
                    correct_index = q_data.get('correct', 0)
                    if int(user_answer) == correct_index:
                        score += 1

            # Natijani saqlash
            TestAttempt.objects.create(
                user=request.user,
                ai_test=ai_test,
                score=score,
                total_questions=len(questions_data)
            )

            messages.success(request, f"Test yakunlandi! Natija: {score}/{len(questions_data)}")

            # TO'G'RI URL NOMI: app3:test_result
            return redirect('app3:test_result', test_id=test_id)
        else:
            messages.error(request, "Testni ishlash uchun tizimga kiring")
            return redirect('login')

    return render(request, 'app3/take_test.html', {
        'ai_test': ai_test,
        'questions': ai_test.questions_data,
    })

@login_required
def test_result(request, test_id):
    """Test natijasi"""
    ai_test = get_object_or_404(AITest, id=test_id)

    # Foydalanuvchining oxirgi natijasi
    user_result = TestAttempt.objects.filter(
        user=request.user,
        ai_test=ai_test
    ).order_by('-created_at').first()

    return render(request, 'app3/test_result.html', {
        'ai_test': ai_test,
        'user_result': user_result,
    })


# app3/views.py - my_results funksiyasini yangilaymiz

@login_required
def my_results(request):
    """Foydalanuvchi natijalari"""
    results = TestAttempt.objects.filter(user=request.user).select_related('ai_test').order_by('-created_at')

    # Umumiy statistikalarni hisoblash
    total_tests = results.count()
    total_score = 0
    total_questions = 0
    total_percentage = 0

    for result in results:
        total_score += result.score
        total_questions += result.total_questions
        total_percentage += result.percentage()

    # O'rtacha foiz
    average_percentage = 0
    if total_tests > 0:
        average_percentage = round(total_percentage / total_tests, 1)

    # Umumiy natija
    overall_result = f"{total_score}/{total_questions}"

    return render(request, 'app3/my_results.html', {
        'results': results,
        'total_tests': total_tests,
        'overall_result': overall_result,
        'average_percentage': average_percentage,
        'attempts_count': total_tests,  # Urinishlar soni = testlar soni
    })

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_test(request, test_id):
    """Testni o'chirish"""
    ai_test = get_object_or_404(AITest, id=test_id)
    topic = ai_test.topic
    ai_test.delete()

    messages.success(request, f"'{topic}' testi o'chirildi")
    return redirect('home')


def about(request):
    """Loyiha haqida"""
    return render(request, 'app3/about.html')


# app3/views.py - test_statistics funksiyasini yangilaymiz

@login_required
@user_passes_test(lambda u: u.is_staff)
def test_statistics(request, test_id):
    """Test statistikasi (admin uchun)"""
    ai_test = get_object_or_404(AITest, id=test_id)

    # Testni yechgan foydalanuvchilar
    attempts = TestAttempt.objects.filter(ai_test=ai_test).select_related('user').order_by('-score', '-created_at')

    # Savollar soni
    questions_count = len(ai_test.questions_data)

    # Statistik ma'lumotlar
    total_attempts = attempts.count()
    average_score = 0
    best_score = 0
    worst_score = 0

    if total_attempts > 0:
        total_percentage = sum(attempt.percentage() for attempt in attempts)
        average_score = round(total_percentage / total_attempts, 1)

        scores = [attempt.percentage() for attempt in attempts]
        best_score = max(scores)
        worst_score = min(scores)

    # Ballar bo'yicha taqsimot va foizlarni hisoblash
    score_distribution = {}
    if questions_count > 0:
        score_distribution = {
            '90-100': {
                'count': attempts.filter(score__gte=questions_count * 0.9).count(),
            },
            '80-89': {
                'count': attempts.filter(
                    score__gte=questions_count * 0.8,
                    score__lt=questions_count * 0.9
                ).count(),
            },
            '70-79': {
                'count': attempts.filter(
                    score__gte=questions_count * 0.7,
                    score__lt=questions_count * 0.8
                ).count(),
            },
            '60-69': {
                'count': attempts.filter(
                    score__gte=questions_count * 0.6,
                    score__lt=questions_count * 0.7
                ).count(),
            },
            '0-59': {
                'count': attempts.filter(
                    score__lt=questions_count * 0.6
                ).count(),
            },
        }

        # Har bir kategoriya uchun foizni hisoblash
        for key in score_distribution:
            if total_attempts > 0:
                percentage = (score_distribution[key]['count'] / total_attempts) * 100
            else:
                percentage = 0
            score_distribution[key]['percentage'] = round(percentage, 1)
    else:
        # Agar savollar bo'lmasa
        for key in ['90-100', '80-89', '70-79', '60-69', '0-59']:
            score_distribution[key] = {'count': 0, 'percentage': 0}

    return render(request, 'app3/test_statistics.html', {
        'ai_test': ai_test,
        'questions_count': questions_count,
        'attempts': attempts,
        'total_attempts': total_attempts,
        'average_score': average_score,
        'best_score': best_score,
        'worst_score': worst_score,
        'score_distribution': score_distribution,
    })