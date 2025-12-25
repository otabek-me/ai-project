# urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

# i18n_patterns TASHQARISIDAGI URL'lar (tilga bog'liq bo'lmagan)
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

# i18n_patterns ICHIDAGI URL'lar (tilga bog'liq)
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('', include('app1.urls'), name='app1'),
    path('users/', include('users.urls'), name='users'),
    path('code/', include('app2.urls'), name='code'),
    path('ai', include('app3.urls')),  # app3 ga o'zgartiramiz

)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)