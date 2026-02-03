// Morning Quiz Bot - Admin Panel
// Main Application Script

// Global State
let allQuestions = [];
let allCategories = [];
let allChats = [];
let charts = {};

// Pagination for questions
let currentQuestionsPage = 1;
let questionsPerPage = 50;

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    initDarkMode();
    initNavigation();
    initMobileMenu();
    loadDashboard();
});

// ========== Dark Mode ==========
function initDarkMode() {
    const isDark = localStorage.getItem('darkMode') === 'true';
    if (isDark) {
        document.body.classList.add('dark-mode');
    }
    
    const toggle = document.getElementById('darkModeToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        });
    }
}

// ========== Toast Notifications ==========
function showToast(message, type = 'info') {
    // Ищем content-header в активной секции
    const activeSection = document.querySelector('.section.active');
    let contentHeader = null;
    
    if (activeSection) {
        contentHeader = activeSection.querySelector('.content-header');
    }
    
    // Если не нашли content-header, используем стандартный контейнер
    if (!contentHeader) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span style="font-size: 1.25rem;">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
            <span style="font-size: 0.875rem;">${message}</span>
        `;
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease-out reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
        return;
    }
    
    // Создаем toast внутри content-header
    const toast = document.createElement('div');
    toast.className = `toast toast-header ${type}`;
    toast.innerHTML = `
        <span style="font-size: 0.875rem;">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
        <span style="font-size: 0.8125rem;">${message}</span>
    `;
    
    // Позиционируем абсолютно внутри content-header
    contentHeader.style.position = 'relative';
    toast.style.position = 'absolute';
    toast.style.top = '0';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%) translateY(-100%)';
    toast.style.zIndex = '1000';
    toast.style.marginTop = '0';
    toast.style.opacity = '0';
    
    contentHeader.appendChild(toast);
    
    // Анимация появления сверху вниз
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(-50%) translateY(0)';
    });
    
    // Удаляем через 3 секунды
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(-20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ========== Navigation ==========
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const sectionId = item.getAttribute('data-section');
            showSection(sectionId);
            
            // Закрываем меню на мобильных устройствах после выбора раздела
            if (window.innerWidth <= 768) {
                const sidebar = document.getElementById('sidebar');
                const burger = document.getElementById('mobileMenuToggle');
                if (sidebar) sidebar.classList.remove('open');
                if (burger) burger.classList.remove('open');
            }
        });
    });
}

// Mobile burger menu
function initMobileMenu() {
    const burger = document.getElementById('mobileMenuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (!burger || !sidebar) return;
    
    function toggleMenu(isOpen) {
        sidebar.classList.toggle('open', isOpen);
        burger.classList.toggle('open', isOpen);
        if (overlay) {
            overlay.classList.toggle('active', isOpen);
        }
    }
    
    // Toggle menu on burger click
    burger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = !sidebar.classList.contains('open');
        toggleMenu(isOpen);
    });
    
    // Close menu when clicking on overlay
    if (overlay) {
        overlay.addEventListener('click', () => {
            toggleMenu(false);
        });
    }
    
    // Close menu when clicking outside (fallback)
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 768 && sidebar.classList.contains('open')) {
            // Если клик не по сайдбару и не по бургеру
            if (!sidebar.contains(e.target) && !burger.contains(e.target) && !overlay?.contains(e.target)) {
                toggleMenu(false);
            }
        }
    });
    
    // Prevent sidebar clicks from closing menu
    sidebar.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

function showSection(sectionId) {
    // Update navigation
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
    const activeNav = document.querySelector(`[data-section="${sectionId}"]`);
    if (activeNav) activeNav.classList.add('active');
    
    // Update sections
    document.querySelectorAll('.section').forEach(section => section.classList.remove('active'));
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
        
        // Load section data
        switch(sectionId) {
            case 'dashboard':
                loadDashboard();
                break;
            case 'questions':
                loadQuestions();
                break;
            case 'malformed-questions':
                loadMalformedQuestions();
                break;
            case 'bot-metrics':
                loadBotMetrics();
                break;
            case 'chats':
                loadChats();
                break;
            case 'photo-quiz':
                loadPhotoQuiz();
                break;
            case 'analytics':
                loadAnalytics();
                break;
            case 'users':
                loadUsers();
                break;
            case 'settings':
                loadSettings();
                break;
        }
    }
}

// ========== Dashboard ==========
async function loadDashboard() {
    try {
        const response = await fetch('/api/analytics/dashboard');
        const data = await response.json();
        
        // Основные метрики
        const totalUsersEl = document.getElementById('totalUsers');
        if (totalUsersEl) totalUsersEl.textContent = data.total_users || 0;
        
        const totalQuizzesEl = document.getElementById('totalQuizzes');
        if (totalQuizzesEl) totalQuizzesEl.textContent = data.total_quizzes || 0;
        
        const totalQuestionsDBEl = document.getElementById('totalQuestionsDB');
        if (totalQuestionsDBEl) totalQuestionsDBEl.textContent = data.total_questions_db || 0;
        
        const totalPhotoQuizEl = document.getElementById('totalPhotoQuiz');
        if (totalPhotoQuizEl) totalPhotoQuizEl.textContent = data.total_photo_quiz || 0;
        
        const totalChatsEl = document.getElementById('totalChats');
        if (totalChatsEl) totalChatsEl.textContent = data.total_chats || 0;
        
        const totalScoreEl = document.getElementById('totalScore');
        if (totalScoreEl) totalScoreEl.textContent = data.total_score || 0;
        
        // Дополнительные метрики
        const avgActivityEl = document.getElementById('avgActivityUsers');
        if (avgActivityEl) {
            avgActivityEl.textContent = data.avg_answered_per_user ? `Среднее: ${data.avg_answered_per_user} ответов/пользователь` : '';
        }
        
        const avgAnsweredEl = document.getElementById('avgAnswered');
        if (avgAnsweredEl) {
            avgAnsweredEl.textContent = `Всего ответов: ${data.total_quizzes || 0}`;
        }
        
        const categoriesInfoEl = document.getElementById('categoriesInfo');
        if (categoriesInfoEl) {
            categoriesInfoEl.textContent = `В ${data.total_categories || 0} категориях`;
        }
        
        const avgScoreEl = document.getElementById('avgScore');
        if (avgScoreEl) {
            avgScoreEl.textContent = data.avg_score_per_user ? `Среднее: ${data.avg_score_per_user} баллов/пользователь` : '';
        }
        
        const activeSubscriptionsEl = document.getElementById('activeSubscriptions');
        if (activeSubscriptionsEl) {
            activeSubscriptionsEl.textContent = `${data.active_chats_with_subscription || 0} с подпиской`;
        }
        
        // Статус бота
        updateBotStatusDisplay(data.bot_enabled, data.bot_mode, data.active_quizzes_count);
        
        await loadCharts();
        showToast('Панель управления загружена', 'success');
    } catch (error) {
        console.error('Error loading dashboard:', error);
        showToast('Ошибка загрузки панели', 'error');
        updateBotStatusDisplay(false, 'unknown', 0);
    }
}

function updateBotStatusDisplay(enabled, mode, activeQuizzes) {
    const statusIcon = document.getElementById('botStatusIcon');
    const statusText = document.getElementById('botStatusText');
    
    if (!statusIcon || !statusText) return;
    
    if (enabled) {
        statusIcon.textContent = '🟢';
        statusText.innerHTML = `<span style="color: var(--success); font-weight: 600;">✓ Бот включен</span> | Режим: <strong>${mode === 'main' ? 'Основной' : 'Обслуживание'}</strong> | Активных викторин: <strong>${activeQuizzes || 0}</strong>`;
    } else {
        statusIcon.textContent = '🔴';
        statusText.innerHTML = `<span style="color: var(--danger); font-weight: 600;">✗ Бот выключен</span> | Режим: <strong>${mode === 'main' ? 'Основной' : 'Обслуживание'}</strong>`;
    }
}

function refreshDashboard() {
    loadDashboard();
}

async function loadCharts() {
    // Destroy existing charts - проверяем через Chart.getChart перед уничтожением
    const chartIds = ['activityChart', 'categoriesChart', 'usersChart', 'scoreDistChart'];
    chartIds.forEach(id => {
        const canvas = document.getElementById(id);
        if (canvas) {
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
                existingChart.destroy();
            }
        }
    });
    
    // Также уничтожаем из объекта charts
    Object.values(charts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            try {
            chart.destroy();
            } catch(e) {
                // Игнорируем ошибки при уничтожении
            }
        }
    });
    charts = {};
    
    try {
        const [activityRes, categoriesRes, usersRes, scoresRes] = await Promise.all([
            fetch('/api/analytics/charts/activity'),
            fetch('/api/analytics/charts/categories'),
            fetch('/api/analytics/charts/users'),
            fetch('/api/analytics/charts/score-distribution')
        ]);
        
        const activity = await activityRes.json();
        const categories = await categoriesRes.json();
        const users = await usersRes.json();
        const scores = await scoresRes.json();
        
        const isDark = document.body.classList.contains('dark-mode');
        const textColor = isDark ? '#e5e7eb' : '#374151';
        const gridColor = isDark ? '#374151' : '#e5e7eb';
        const bgColor = isDark ? '#1f2937' : '#ffffff';
        
        // Activity Chart - Ответы по чатам
        const activityCtx = document.getElementById('activityChart');
        const activityContainer = activityCtx?.parentElement;
        
        if (activityCtx) {
            // Убеждаемся, что canvas не используется
            const existingActivityChart = Chart.getChart(activityCtx);
            if (existingActivityChart) {
                existingActivityChart.destroy();
            }
            
            if (activity.labels && activity.labels.length > 0 && activity.data && activity.data.length > 0) {
            charts.activity = new Chart(activityCtx, {
                    type: 'bar',
                data: {
                        labels: activity.labels.map(l => l.length > 20 ? l.substring(0, 20) + '...' : l),
                    datasets: [{
                            label: 'Ответов',
                        data: activity.data,
                            backgroundColor: 'rgba(99, 102, 241, 0.8)',
                        borderColor: '#6366f1',
                            borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                        indexAxis: 'y',
                        plugins: { 
                            legend: { display: false },
                            title: { display: true, text: `Всего: ${activity.total_answered || 0} ответов`, color: textColor, font: { size: 14 } }
                        },
                    scales: {
                            x: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } },
                            y: { ticks: { color: textColor, font: { size: 10 } }, grid: { display: false } }
                    }
                }
            });
            } else {
                if (activityContainer) {
                    activityContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">📊 Нет данных для отображения</div>';
                }
            }
        }
        
        // Categories Chart - Вопросы по категориям
        const categoriesCtx = document.getElementById('categoriesChart');
        const categoriesContainer = categoriesCtx?.parentElement;
        
        if (categoriesCtx) {
            // Убеждаемся, что canvas не используется
            const existingCategoriesChart = Chart.getChart(categoriesCtx);
            if (existingCategoriesChart) {
                existingCategoriesChart.destroy();
            }
            
            if (categories.labels && categories.labels.length > 0 && categories.data && categories.data.length > 0) {
            charts.categories = new Chart(categoriesCtx, {
                type: 'bar',
                data: {
                        labels: categories.labels.map(l => l.length > 20 ? l.substring(0, 20) + '...' : l),
                        datasets: [{ 
                            label: 'Вопросов', 
                            data: categories.data, 
                            backgroundColor: 'rgba(16, 185, 129, 0.8)',
                            borderColor: '#10b981',
                            borderWidth: 1
                        }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                        indexAxis: 'y',
                        plugins: { 
                            legend: { display: false },
                            title: { display: true, text: `Всего: ${categories.total_questions || 0} вопросов в ${categories.total_categories || 0} категориях`, color: textColor, font: { size: 14 } }
                        },
                    scales: {
                            x: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } },
                            y: { ticks: { color: textColor, font: { size: 10 } }, grid: { display: false } }
                    }
                }
            });
            } else {
                if (categoriesContainer) {
                    categoriesContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">📊 Нет данных для отображения</div>';
                }
            }
        }
        
        // Users Chart - Топ пользователей по баллам
        const usersCtx = document.getElementById('usersChart');
        const usersContainer = usersCtx?.parentElement;
        
        if (usersCtx) {
            // Убеждаемся, что canvas не используется
            const existingUsersChart = Chart.getChart(usersCtx);
            if (existingUsersChart) {
                existingUsersChart.destroy();
            }
            
            if (users.labels && users.labels.length > 0 && users.data && users.data.length > 0) {
                const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#06b6d4', '#84cc16'];
            charts.users = new Chart(usersCtx, {
                type: 'doughnut',
                data: {
                        labels: users.labels.map(l => l.length > 15 ? l.substring(0, 15) + '...' : l),
                    datasets: [{
                        data: users.data,
                            backgroundColor: colors.slice(0, users.labels.length)
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                        plugins: { 
                            legend: { 
                                position: 'right',
                                labels: { color: textColor, font: { size: 10 }, boxWidth: 12 }
                            },
                            title: { display: true, text: `Топ ${users.labels.length} из ${users.total_users || 0} пользователей`, color: textColor, font: { size: 14 } }
                        }
                    }
                });
            } else {
                if (usersContainer) {
                    usersContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">📊 Нет данных для отображения</div>';
                }
            }
        }
        
        // Score Distribution Chart
        const scoresCtx = document.getElementById('scoreDistChart');
        const scoresContainer = scoresCtx?.parentElement;
        
        if (scoresCtx) {
            // Убеждаемся, что canvas не используется
            const existingScoresChart = Chart.getChart(scoresCtx);
            if (existingScoresChart) {
                existingScoresChart.destroy();
            }
            
            if (scores.labels && scores.labels.length > 0 && scores.data && scores.data.length > 0 && scores.data.some(v => v > 0)) {
            charts.scores = new Chart(scoresCtx, {
                    type: 'pie',
                data: {
                    labels: scores.labels,
                        datasets: [{ 
                            data: scores.data, 
                            backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
                        }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                        plugins: { 
                            legend: { 
                                position: 'right',
                                labels: { color: textColor, font: { size: 11 } }
                            },
                            title: { display: true, text: 'Распределение баллов', color: textColor, font: { size: 14 } }
                    }
                }
            });
            } else {
                if (scoresContainer) {
                    scoresContainer.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-secondary);">📊 Нет данных для отображения</div>';
                }
            }
        }
    } catch (error) {
        console.error('Error loading charts:', error);
        // Показываем сообщения об ошибке в контейнерах графиков
        const chartContainers = [
            { id: 'activityChart', name: 'Активность' },
            { id: 'categoriesChart', name: 'Категории' },
            { id: 'usersChart', name: 'Пользователи' },
            { id: 'scoreDistChart', name: 'Распределение баллов' }
        ];
        
        chartContainers.forEach(({ id, name }) => {
            const ctx = document.getElementById(id);
            const container = ctx?.parentElement;
            if (container && !charts[name.toLowerCase()]) {
                container.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--danger);">❌ Ошибка загрузки данных</div>`;
            }
        });
    }
}

// ========== Questions Management ==========
async function loadQuestions() {
    try {
        // Сбрасываем фильтр категории при загрузке всех вопросов
        currentFilteredCategory = null;
        
        const [questionsRes, categoriesRes] = await Promise.all([
            fetch('/api/questions'),
            fetch('/api/categories')
        ]);
        
        if (!questionsRes.ok || !categoriesRes.ok) {
            throw new Error('Ошибка загрузки данных');
        }
        
        const questionsData = await questionsRes.json();
        const categoriesData = await categoriesRes.json();
        
        // Правильно извлекаем массив вопросов
        if (Array.isArray(questionsData)) {
            allQuestions = questionsData;
        } else if (questionsData.questions && Array.isArray(questionsData.questions)) {
            allQuestions = questionsData.questions;
        } else {
            console.error('Unexpected questions data format:', questionsData);
            allQuestions = [];
        }
        
        // Правильно извлекаем массив категорий
        if (Array.isArray(categoriesData)) {
            allCategories = categoriesData;
        } else if (categoriesData.categories && Array.isArray(categoriesData.categories)) {
            allCategories = categoriesData.categories;
        } else {
            console.error('Unexpected categories data format:', categoriesData);
            allCategories = [];
        }
        
        // Отладочный вывод для проверки структуры данных
        if (allQuestions.length > 0) {
            console.log('Sample question:', allQuestions[0]);
            console.log('Question has options:', allQuestions[0].options);
            console.log('Question has answers:', allQuestions[0].answers);
        }
        
        renderCategoriesList();
        renderQuestions(allQuestions);
        
        // Скрываем информацию о категории при загрузке всех вопросов
        const info = document.getElementById('currentCategoryInfo');
        if (info) {
            info.style.display = 'none';
        }
        
        showToast(`Загружено ${allQuestions.length} вопросов`, 'success');
    } catch (error) {
        console.error('Error loading questions:', error);
        showToast('Ошибка загрузки вопросов', 'error');
    }
}

// ========== Malformed Questions Management ==========
async function loadMalformedQuestions() {
    const container = document.getElementById('malformedQuestionsContainer');
    const statsElement = document.getElementById('malformedStats');
    
    // Показываем индикатор загрузки
    if (container) {
        container.innerHTML = '<p style="text-align: center; padding: 2rem;">Загрузка...</p>';
    }
    if (statsElement) {
        statsElement.innerHTML = 'Загрузка...';
    }
    
    try {
        const response = await fetch('/api/malformed-questions');
        
        if (!response.ok) {
            // Пытаемся получить детали ошибки из ответа
            let errorMessage = `Ошибка ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.detail) {
                    errorMessage = errorData.detail;
                }
            } catch (e) {
                // Если не удалось распарсить JSON, используем стандартное сообщение
            }
            throw new Error(errorMessage);
        }
        
        const data = await response.json();
        const malformedQuestions = data.malformed_questions || [];
        const groupedByError = data.grouped_by_error || {};
        
        // Обновляем статистику
        if (statsElement) {
            const total = malformedQuestions.length;
            const errorTypesCount = Object.keys(groupedByError).length;
            statsElement.innerHTML = `
                Всего бракованных вопросов: <strong>${total}</strong><br>
                Типов ошибок: <strong>${errorTypesCount}</strong>
            `;
        }
        
        // Отображаем бракованные вопросы
        renderMalformedQuestions(malformedQuestions, groupedByError);
        
        if (malformedQuestions.length === 0) {
            showToast('Бракованных вопросов не найдено', 'success');
        } else {
            showToast(`Загружено ${malformedQuestions.length} бракованных вопросов`, 'info');
        }
    } catch (error) {
        console.error('Error loading malformed questions:', error);
        const errorMessage = error.message || 'Неизвестная ошибка';
        showToast(`Ошибка загрузки: ${errorMessage}`, 'error');
        
        if (container) {
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 2rem;">
                    <p style="color: var(--danger); font-size: 1.1rem; margin-bottom: 0.5rem;">❌ Ошибка загрузки данных</p>
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">${escapeHtml(errorMessage)}</p>
                    <button class="btn btn-secondary" onclick="loadMalformedQuestions()" style="margin-top: 1rem;">
                        🔄 Попробовать снова
                    </button>
                </div>
            `;
        }
        if (statsElement) {
            statsElement.innerHTML = '<span style="color: var(--danger);">Ошибка загрузки</span>';
        }
    }
}

function renderMalformedQuestions(malformedQuestions, groupedByError) {
    const container = document.getElementById('malformedQuestionsContainer');
    if (!container) return;
    
    if (malformedQuestions.length === 0) {
        container.innerHTML = `
            <div class="card" style="text-align: center; padding: 2rem;">
                <p style="color: var(--text-secondary); font-size: 1.1rem; margin-bottom: 0.5rem;">✅ Бракованных вопросов не найдено</p>
                <p style="color: var(--text-secondary); font-size: 0.875rem;">Все вопросы прошли валидацию успешно</p>
            </div>
        `;
        return;
    }
    
    // Группируем по типу ошибки для отображения
    let html = '';
    
    // Сначала показываем сводку по типам ошибок
    html += `
        <div class="card" style="margin-bottom: 1.5rem;">
            <h3 style="margin-bottom: 1rem; font-size: 1rem;">Типы ошибок</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
    `;
    
    for (const [errorType, entries] of Object.entries(groupedByError)) {
        const errorTypeLabel = getErrorTypeLabel(errorType);
        html += `
            <div style="padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-weight: 600; margin-bottom: 0.5rem;">${errorTypeLabel}</div>
                <div style="font-size: 1.5rem; color: var(--primary);">${entries.length}</div>
            </div>
        `;
    }
    
    html += `
            </div>
        </div>
    `;
    
    // Затем показываем детальный список
    html += `
        <div class="card">
            <h3 style="margin-bottom: 1rem; font-size: 1rem;">Детальный список</h3>
    `;
    
    for (const entry of malformedQuestions) {
        const errorType = entry.error_type || 'unknown';
        const errorTypeLabel = getErrorTypeLabel(errorType);
        const category = entry.category || 'Неизвестная категория';
        const error = entry.error || '';
        const data = entry.data || {};
        
        html += `
            <div style="padding: 1rem; margin-bottom: 1rem; background: var(--bg-secondary); border-radius: 8px; border-left: 4px solid var(--danger);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                    <div style="flex: 1;">
                        <div style="font-weight: 600; margin-bottom: 0.25rem;">
                            <span style="color: var(--danger);">⚠️</span> ${errorTypeLabel}
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary);">
                            Категория: <strong>${escapeHtml(category)}</strong>
                        </div>
                    </div>
                </div>
        `;
        
        if (error) {
            html += `
                <div style="margin-top: 0.5rem; padding: 0.75rem; background: var(--bg-primary); border-radius: 6px;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Ошибка:</div>
                    <div style="font-size: 0.875rem; color: var(--danger); font-family: monospace;">${escapeHtml(error)}</div>
                </div>
            `;
        }
        
        if (data && Object.keys(data).length > 0) {
            html += `
                <div style="margin-top: 0.5rem; padding: 0.75rem; background: var(--bg-primary); border-radius: 6px;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Данные:</div>
                    <pre style="font-size: 0.75rem; color: var(--text-primary); overflow-x: auto; margin: 0;">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
                </div>
            `;
        }
        
        html += `
            </div>
        `;
    }
    
    html += `
        </div>
    `;
    
    container.innerHTML = html;
}

function getErrorTypeLabel(errorType) {
    const labels = {
        'invalid_question': 'Невалидный вопрос',
        'category_not_list': 'Категория не является списком',
        'load_error': 'Ошибка загрузки',
        'unknown': 'Неизвестная ошибка'
    };
    return labels[errorType] || errorType;
}

// ========== Bot Metrics Management ==========
async function loadBotMetrics() {
    const statusContainer = document.getElementById('botMetricsStatus');
    const detailsContainer = document.getElementById('botMetricsDetails');
    
    // Показываем индикатор загрузки
    if (statusContainer) {
        statusContainer.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Загрузка...</p>';
    }
    if (detailsContainer) {
        detailsContainer.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Загрузка...</p>';
    }
    
    try {
        const [metricsResponse, healthResponse] = await Promise.all([
            fetch('/api/bot/metrics'),
            fetch('/api/bot/health')
        ]);
        
        if (!metricsResponse.ok) {
            throw new Error(`Ошибка ${metricsResponse.status}: ${metricsResponse.statusText}`);
        }
        
        const metrics = await metricsResponse.json();
        const health = healthResponse.ok ? await healthResponse.json() : { status: 'unknown' };
        
        // Обновляем статус бота
        if (statusContainer) {
            const status = health.status || metrics.bot_status || 'unknown';
            let statusHtml = '';
            let statusColor = '';
            let statusIcon = '';
            let statusText = '';
            
            switch(status) {
                case 'healthy':
                    statusColor = 'var(--success)';
                    statusIcon = '✅';
                    statusText = 'Бот работает нормально';
                    break;
                case 'degraded':
                    statusColor = 'var(--warning)';
                    statusIcon = '⚠️';
                    statusText = 'Есть проблемы';
                    break;
                case 'critical':
                    statusColor = 'var(--danger)';
                    statusIcon = '🔴';
                    statusText = 'Критическое состояние';
                    break;
                case 'offline':
                    statusColor = 'var(--text-secondary)';
                    statusIcon = '⚫';
                    statusText = 'Бот не запущен';
                    break;
                default:
                    statusColor = 'var(--text-secondary)';
                    statusIcon = '❓';
                    statusText = 'Неизвестный статус';
            }
            
            statusHtml = `
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span style="font-size: 2rem;">${statusIcon}</span>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; font-size: 1.1rem; color: ${statusColor}; margin-bottom: 0.25rem;">
                            ${statusText}
                        </div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary);">
                            Статус: <strong>${status}</strong>
                        </div>
                    </div>
                </div>
            `;
            
            statusContainer.innerHTML = statusHtml;
        }
        
        // Обновляем метрики
        if (metrics.timeout_stats) {
            document.getElementById('timeoutErrors').textContent = 
                metrics.timeout_stats.errors || 0;
            document.getElementById('retryAttempts').textContent = 
                metrics.timeout_stats.retry_attempts || 0;
        } else {
            document.getElementById('timeoutErrors').textContent = '0';
            document.getElementById('retryAttempts').textContent = '0';
        }
        
        // Обновляем uptime
        if (metrics.bot_uptime_seconds) {
            const hours = Math.floor(metrics.bot_uptime_seconds / 3600);
            const minutes = Math.floor((metrics.bot_uptime_seconds % 3600) / 60);
            const seconds = metrics.bot_uptime_seconds % 60;
            document.getElementById('botUptime').textContent = 
                `${hours}ч ${minutes}м ${Math.floor(seconds)}с`;
        } else {
            document.getElementById('botUptime').textContent = '-';
        }
        
        // Обновляем PID
        if (metrics.bot_pid) {
            document.getElementById('botProcess').textContent = metrics.bot_pid;
        } else {
            document.getElementById('botProcess').textContent = '-';
        }
        
        // Обновляем детальную информацию
        if (detailsContainer) {
            let detailsHtml = '<div style="display: grid; gap: 1rem;">';
            
            if (metrics.timestamp) {
                detailsHtml += `
                    <div>
                        <strong>Время обновления:</strong> ${new Date(metrics.timestamp).toLocaleString('ru-RU')}
                    </div>
                `;
            }
            
            if (metrics.bot_running !== undefined) {
                detailsHtml += `
                    <div>
                        <strong>Процесс запущен:</strong> ${metrics.bot_running ? '✅ Да' : '❌ Нет'}
                    </div>
                `;
            }
            
            if (metrics.timeout_stats) {
                detailsHtml += `
                    <div>
                        <strong>Ошибки таймаута:</strong> ${metrics.timeout_stats.errors || 0}
                    </div>
                    <div>
                        <strong>Предупреждения:</strong> ${metrics.timeout_stats.warnings || 0}
                    </div>
                    <div>
                        <strong>Повторные попытки:</strong> ${metrics.timeout_stats.retry_attempts || 0}
                    </div>
                `;
                
                if (metrics.timeout_stats.log_file) {
                    detailsHtml += `
                        <div>
                            <strong>Лог-файл:</strong> ${escapeHtml(metrics.timeout_stats.log_file)}
                        </div>
                    `;
                }
            }
            
            if (metrics.rate_limiter) {
                detailsHtml += `
                    <div>
                        <strong>Rate Limiter:</strong> Активен
                    </div>
                `;
            }
            
            if (metrics.error) {
                detailsHtml += `
                    <div style="color: var(--danger);">
                        <strong>Ошибка:</strong> ${escapeHtml(metrics.error)}
                    </div>
                `;
            }
            
            detailsHtml += '</div>';
            detailsContainer.innerHTML = detailsHtml;
        }
        
        showToast('Метрики обновлены', 'success');
    } catch (error) {
        console.error('Error loading bot metrics:', error);
        const errorMessage = error.message || 'Неизвестная ошибка';
        showToast(`Ошибка загрузки метрик: ${errorMessage}`, 'error');
        
        if (statusContainer) {
            statusContainer.innerHTML = `
                <div style="text-align: center; padding: 1rem;">
                    <p style="color: var(--danger); font-size: 1.1rem; margin-bottom: 0.5rem;">❌ Ошибка загрузки</p>
                    <p style="color: var(--text-secondary); font-size: 0.875rem;">${escapeHtml(errorMessage)}</p>
                    <button class="btn btn-secondary" onclick="loadBotMetrics()" style="margin-top: 1rem;">
                        🔄 Попробовать снова
                    </button>
                </div>
            `;
        }
        
        if (detailsContainer) {
            detailsContainer.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Ошибка загрузки данных</p>';
        }
    }
}

function renderCategoriesList() {
    const container = document.getElementById('categoriesList');
    if (!container) return;
    
    if (!allCategories || allCategories.length === 0) {
        container.innerHTML = `
            <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.5rem;">Нет категорий</p>
            <button class="btn btn-sm btn-primary" onclick="addNewCategory()" style="width: 100%; font-size: 0.8rem;">➕ Создать категорию</button>
        `;
        return;
    }
    
    container.innerHTML = `
        <button class="btn btn-sm btn-primary" onclick="addNewCategory()" style="width: 100%; margin-bottom: 0.75rem; font-size: 0.8rem;">➕ Создать категорию</button>
        ${allCategories.map(cat => `
            <div class="category-item" style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; margin-bottom: 0.5rem; border-radius: 6px; background: var(--bg-secondary); cursor: pointer;" onclick="filterByCategory('${cat.name}')">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(cat.name)}</div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${cat.question_count || 0} вопросов</div>
                </div>
                <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); deleteCategory('${cat.name}')" title="Удалить категорию" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;">🗑️</button>
            </div>
        `).join('')}
    `;
}

async function addNewCategory() {
    const categoryName = prompt('Введите название новой категории:');
    if (!categoryName || !categoryName.trim()) {
        return;
    }
    
    try {
        const response = await fetch(`/api/categories?category_name=${encodeURIComponent(categoryName.trim())}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(result.message || 'Категория создана', 'success');
            loadQuestions(); // Перезагружаем список
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error creating category:', error);
    }
}

async function deleteCategory(categoryName) {
    if (!confirm(`Удалить категорию "${categoryName}" и все её вопросы?\n\nЭто действие нельзя отменить!`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/categories/${encodeURIComponent(categoryName)}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(result.message || 'Категория удалена', 'success');
            loadQuestions(); // Перезагружаем список
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error deleting category:', error);
    }
}

let currentFilteredCategory = null;

function filterByCategory(categoryName) {
    const filtered = allQuestions.filter(q => q.category === categoryName || q.original_category === categoryName);
    currentFilteredCategory = categoryName;
    renderQuestions(filtered);
    
    const info = document.getElementById('currentCategoryInfo');
    const nameEl = document.getElementById('currentCategoryName');
    const countEl = document.getElementById('currentCategoryCount');
    
    if (info && nameEl && countEl) {
        info.style.display = 'block';
        nameEl.textContent = categoryName;
        countEl.textContent = `(${filtered.length} вопросов)`;
    }
}

function showAllQuestions() {
    currentFilteredCategory = null;
    renderQuestions(allQuestions);
    const info = document.getElementById('currentCategoryInfo');
    if (info) {
        info.style.display = 'none';
    }
}

function renderQuestions(questions) {
    const container = document.getElementById('questionsContainer');
    const search = document.getElementById('questionSearch')?.value?.toLowerCase() || '';

    let filtered = questions;
    if (search) {
        filtered = questions.filter(q =>
            (q.question && q.question.toLowerCase().includes(search)) ||
            (q.correct && q.correct.toLowerCase().includes(search))
        );
    }

    if (filtered.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">Нет вопросов</p>';
        return;
    }

    // Пагинация
    const totalPages = Math.ceil(filtered.length / questionsPerPage);
    currentQuestionsPage = Math.min(currentQuestionsPage, totalPages);
    currentQuestionsPage = Math.max(1, currentQuestionsPage);

    const startIdx = (currentQuestionsPage - 1) * questionsPerPage;
    const endIdx = startIdx + questionsPerPage;
    const displayQuestions = filtered.slice(startIdx, endIdx);
    
    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 50%;">Вопрос</th>
                    <th style="width: 15%;">Варианты</th>
                    <th style="width: 20%;">Ответ</th>
                    <th style="width: 15%;">Действия</th>
                </tr>
            </thead>
            <tbody>
                ${displayQuestions.map((q, idx) => {
                    const category = q.category || q.original_category || 'Unknown';
                    const correctAnswer = q.correct || q.correct_answer || '';
                    
                    // Правильно определяем количество вариантов
                    let options = q.options || q.answers || [];
                    if (!Array.isArray(options)) {
                        options = [];
                    }
                    const optionsCount = options.length;
                    
                    // Отладочный вывод для проблемных вопросов
                    if (optionsCount === 0 && q.question) {
                        console.warn('Question with no options:', {
                            question: q.question,
                            hasOptions: !!q.options,
                            hasAnswers: !!q.answers,
                            options: q.options,
                            answers: q.answers,
                            fullQuestion: q
                        });
                    }
                    
                    // Сохраняем полную информацию о вопросе в data-атрибутах для надежного поиска
                    const questionData = JSON.stringify({
                        category: category,
                        index: q.index !== undefined ? q.index : idx,
                        question: q.question
                    }).replace(/"/g, '&quot;');
                    
                    return `
                        <tr data-question='${questionData}'>
                            <td>${escapeHtml(q.question || '')}</td>
                            <td>
                                <span class="badge" style="background: ${optionsCount > 0 ? 'var(--primary)' : 'var(--danger)'};">
                                    ${optionsCount > 0 ? optionsCount : '0'}
                                </span>
                            </td>
                            <td>
                                <div style="font-weight: 600; color: var(--success);">${escapeHtml(correctAnswer)}</div>
                            </td>
                            <td>
                                <button class="btn btn-sm btn-primary" onclick="editQuestionFromRow(this)" title="Редактировать">✏️</button>
                                <button class="btn btn-sm btn-danger" onclick="deleteQuestionFromRow(this)" title="Удалить">🗑️</button>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>

        <div style="margin-top: 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
            <div style="color: var(--text-secondary); font-size: 0.875rem;">
                Показано ${startIdx + 1}-${Math.min(endIdx, filtered.length)} из ${filtered.length} вопросов
            </div>

            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <label style="font-size: 0.875rem; color: var(--text-secondary);">На странице:</label>
                <select class="form-select" style="width: auto; padding: 0.25rem 0.5rem;" onchange="changeQuestionsPerPage(this.value)">
                    <option value="25" ${questionsPerPage === 25 ? 'selected' : ''}>25</option>
                    <option value="50" ${questionsPerPage === 50 ? 'selected' : ''}>50</option>
                    <option value="100" ${questionsPerPage === 100 ? 'selected' : ''}>100</option>
                    <option value="200" ${questionsPerPage === 200 ? 'selected' : ''}>200</option>
                </select>
            </div>
        </div>

        ${totalPages > 1 ? `
        <div style="margin-top: 1rem; display: flex; justify-content: center; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            <button class="btn btn-secondary" onclick="goToQuestionsPage(${currentQuestionsPage - 1})"
                    ${currentQuestionsPage === 1 ? 'disabled' : ''}
                    style="padding: 0.5rem 0.75rem; font-size: 0.875rem;">
                ← Пред
            </button>

            ${generatePaginationButtons(currentQuestionsPage, totalPages)}

            <button class="btn btn-secondary" onclick="goToQuestionsPage(${currentQuestionsPage + 1})"
                    ${currentQuestionsPage === totalPages ? 'disabled' : ''}
                    style="padding: 0.5rem 0.75rem; font-size: 0.875rem;">
                След →
            </button>
        </div>
        ` : ''}
    `;
}

function generatePaginationButtons(current, total) {
    const maxButtons = 7;
    let start = Math.max(1, current - Math.floor(maxButtons / 2));
    let end = Math.min(total, start + maxButtons - 1);

    if (end - start < maxButtons - 1) {
        start = Math.max(1, end - maxButtons + 1);
    }

    let html = '';

    if (start > 1) {
        html += `<button class="btn btn-secondary" onclick="goToQuestionsPage(1)" style="padding: 0.5rem 0.75rem; font-size: 0.875rem;">1</button>`;
        if (start > 2) {
            html += `<span style="padding: 0.5rem; color: var(--text-secondary);">...</span>`;
        }
    }

    for (let i = start; i <= end; i++) {
        html += `
            <button class="btn ${i === current ? 'btn-primary' : 'btn-secondary'}"
                    onclick="goToQuestionsPage(${i})"
                    style="padding: 0.5rem 0.75rem; font-size: 0.875rem;">
                ${i}
            </button>
        `;
    }

    if (end < total) {
        if (end < total - 1) {
            html += `<span style="padding: 0.5rem; color: var(--text-secondary);">...</span>`;
        }
        html += `<button class="btn btn-secondary" onclick="goToQuestionsPage(${total})" style="padding: 0.5rem 0.75rem; font-size: 0.875rem;">${total}</button>`;
    }

    return html;
}

function goToQuestionsPage(page) {
    currentQuestionsPage = page;
    if (currentFilteredCategory) {
        filterByCategory(currentFilteredCategory);
    } else {
        renderQuestions(allQuestions);
    }
}

function changeQuestionsPerPage(value) {
    questionsPerPage = parseInt(value);
    currentQuestionsPage = 1;
    if (currentFilteredCategory) {
        filterByCategory(currentFilteredCategory);
    } else {
        renderQuestions(allQuestions);
    }
}

function filterQuestions() {
    // Если есть фильтр по категории, применяем его
    if (currentFilteredCategory) {
        const filtered = allQuestions.filter(q => q.category === currentFilteredCategory || q.original_category === currentFilteredCategory);
        renderQuestions(filtered);
    } else {
    renderQuestions(allQuestions);
    }
}

// ========== Question CRUD Functions ==========
let currentEditingQuestion = null;

function addNewQuestion() {
    // Открываем модальное окно для добавления вопроса
    const modal = document.getElementById('addQuestionModal');
    if (!modal) {
        showToast('Модальное окно не найдено. Проверьте HTML.', 'error');
        return;
    }
    
    // Обновляем заголовок
    const title = document.getElementById('addQuestionModalTitle');
    if (title) title.textContent = 'Добавить вопрос';
    
    // Очищаем форму
    const form = modal.querySelector('form');
    if (form) form.reset();
    
    // Заполняем категории
    const categorySelect = document.getElementById('addQuestionCategory');
    if (categorySelect) {
        categorySelect.innerHTML = '<option value="">Выберите категорию</option>';
        if (allCategories && allCategories.length > 0) {
            allCategories.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat.name;
                option.textContent = cat.name;
                categorySelect.appendChild(option);
            });
        }
    }
    
    // Инициализируем варианты ответов (2 пустых)
    const optionsContainer = document.getElementById('addQuestionOptionsContainer');
    if (!optionsContainer) {
        console.error('addQuestionOptionsContainer not found!');
        showToast('Контейнер вариантов ответов не найден', 'error');
        return;
    }
    
    // Очищаем контейнер
    optionsContainer.innerHTML = '';
    
    // Добавляем 2 пустых варианта
    addOptionInput(optionsContainer, '', false);
    addOptionInput(optionsContainer, '', false);
    
    // Очищаем select правильного ответа
    const correctAnswerSelect = document.getElementById('addCorrectAnswer');
    if (correctAnswerSelect) {
        correctAnswerSelect.innerHTML = '<option value="">Выберите правильный ответ</option>';
    }
    
    currentEditingQuestion = null;
    modal.classList.add('active');
    
    // Отладочный вывод
    console.log('Modal opened, options container:', optionsContainer, 'children:', optionsContainer.children.length);
}

async function saveQuestion() {
    const modal = document.getElementById('addQuestionModal');
    if (!modal) return;
    
    const category = document.getElementById('addQuestionCategory')?.value;
    const questionText = document.getElementById('addQuestionText')?.value;
    const explanation = document.getElementById('addExplanation')?.value || '';
    const difficulty = document.getElementById('addDifficulty')?.value || 'medium';
    
    // Собираем варианты ответов
    const options = [];
    const optionInputs = modal.querySelectorAll('.option-input');
    optionInputs.forEach(input => {
        const value = input.value.trim();
        if (value) options.push(value);
    });
    
    const correctAnswer = document.getElementById('addCorrectAnswer')?.value;
    
    // Валидация
    if (!category || !questionText || options.length < 2 || !correctAnswer) {
        showToast('Заполните все обязательные поля (категория, вопрос, минимум 2 варианта ответа, правильный ответ)', 'error');
        return;
    }
    
    if (!options.includes(correctAnswer)) {
        showToast('Правильный ответ должен быть одним из вариантов ответа', 'error');
        return;
    }
    
    try {
        // Если редактируем и категория изменилась, нужно удалить из старой и добавить в новую
        if (currentEditingQuestion && currentEditingQuestion.category !== category) {
            // Сначала удаляем из старой категории
            const deleteResponse = await fetch(`/api/categories/${encodeURIComponent(currentEditingQuestion.category)}/questions/${currentEditingQuestion.index}`, {
                method: 'DELETE'
            });
            
            if (!deleteResponse.ok) {
                const deleteResult = await deleteResponse.json();
                showToast(`Ошибка при удалении из старой категории: ${deleteResult.detail || 'Неизвестная ошибка'}`, 'error');
                return;
            }
            
            // Затем добавляем в новую категорию
            const questionData = {
                question: questionText,
                options: options,
                correct: correctAnswer
            };
            if (explanation && explanation.trim()) {
                questionData.explanation = explanation.trim();
            }
            if (difficulty && difficulty !== 'medium') {
                questionData.difficulty = difficulty;
            }
            
            const addResponse = await fetch(`/api/categories/${encodeURIComponent(category)}/questions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(questionData)
            });
            
            const addResult = await addResponse.json();
            
            if (addResponse.ok) {
                showToast('Вопрос обновлен и перемещен в новую категорию', 'success');
                closeModal('addQuestionModal');
                loadQuestions(); // Перезагружаем список
            } else {
                showToast(`Ошибка: ${addResult.detail || 'Неизвестная ошибка'}`, 'error');
            }
        } else {
            // Обычное обновление или добавление
            const url = currentEditingQuestion 
                ? `/api/categories/${encodeURIComponent(category)}/questions/${currentEditingQuestion.index}`
                : `/api/categories/${encodeURIComponent(category)}/questions`;
            
            const method = currentEditingQuestion ? 'PUT' : 'POST';
            
            const questionData = {
                question: questionText,
                options: options,
                correct: correctAnswer
            };
            if (explanation && explanation.trim()) {
                questionData.explanation = explanation.trim();
            }
            if (difficulty && difficulty !== 'medium') {
                questionData.difficulty = difficulty;
            }
            
            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(questionData)
            });
            
            const result = await response.json();
            
            if (response.ok) {
                showToast(currentEditingQuestion ? 'Вопрос обновлен' : 'Вопрос добавлен', 'success');
                closeModal('addQuestionModal');
                loadQuestions(); // Перезагружаем список
            } else {
                showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
            }
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error saving question:', error);
    }
}

// Новая функция для редактирования из строки таблицы
function editQuestionFromRow(button) {
    const row = button.closest('tr');
    if (!row) {
        showToast('Не удалось найти строку вопроса', 'error');
        return;
    }
    
    const questionDataStr = row.getAttribute('data-question');
    if (!questionDataStr) {
        showToast('Данные вопроса не найдены', 'error');
        return;
    }
    
    try {
        const questionData = JSON.parse(questionDataStr.replace(/&quot;/g, '"'));
        editQuestion(questionData.category, questionData.index, questionData.question);
    } catch (e) {
        console.error('Error parsing question data:', e);
        showToast('Ошибка при чтении данных вопроса', 'error');
    }
}

// Новая функция для удаления из строки таблицы
function deleteQuestionFromRow(button) {
    const row = button.closest('tr');
    if (!row) {
        showToast('Не удалось найти строку вопроса', 'error');
        return;
    }
    
    const questionDataStr = row.getAttribute('data-question');
    if (!questionDataStr) {
        showToast('Данные вопроса не найдены', 'error');
        return;
    }
    
    try {
        const questionData = JSON.parse(questionDataStr.replace(/&quot;/g, '"'));
        deleteQuestion(questionData.category, questionData.index);
    } catch (e) {
        console.error('Error parsing question data:', e);
        showToast('Ошибка при чтении данных вопроса', 'error');
    }
}

async function editQuestion(category, index, questionText = null) {
    console.log('editQuestion called:', { category, index, questionText, allQuestionsLength: allQuestions.length });
    
    // Находим вопрос - используем более надежный поиск
    let question = null;
    
    // Сначала пробуем найти по category и index
    question = allQuestions.find(q => {
        const qCategory = q.category || q.original_category;
        const qIndex = q.index !== undefined ? q.index : null;
        return (qCategory === category) && (qIndex === index || qIndex === parseInt(index));
    });
    
    // Если не нашли и есть текст вопроса, пробуем найти по тексту
    if (!question && questionText) {
        question = allQuestions.find(q => {
            const qCategory = q.category || q.original_category;
            return (qCategory === category) && (q.question === questionText);
        });
    }
    
    // Если все еще не нашли, пробуем найти только по категории и индексу без строгого сравнения
    if (!question) {
        question = allQuestions.find(q => {
            const qCategory = q.category || q.original_category;
            return qCategory === category;
        });
        
        // Если нашли вопрос из нужной категории, используем его index
        if (question) {
            index = question.index !== undefined ? question.index : index;
        }
    }
    
    if (!question) {
        console.error('Question not found:', { 
            category, 
            index, 
            questionText,
            availableCategories: [...new Set(allQuestions.map(q => q.category || q.original_category))],
            sampleQuestions: allQuestions.slice(0, 3).map(q => ({
                category: q.category || q.original_category,
                index: q.index,
                question: q.question?.substring(0, 50)
            }))
        });
        showToast('Вопрос не найден. Попробуйте обновить страницу.', 'error');
        return;
    }
    
    console.log('Question found:', { 
        category: question.category || question.original_category, 
        index: question.index,
        question: question.question?.substring(0, 50)
    });
    
    // Используем реальные данные из найденного вопроса
    const actualCategory = question.category || question.original_category || category;
    const actualIndex = question.index !== undefined ? question.index : parseInt(index);
    
    currentEditingQuestion = { category: actualCategory, index: actualIndex, question };
    
    // Открываем модальное окно
    const modal = document.getElementById('addQuestionModal');
    if (!modal) {
        showToast('Модальное окно не найдено', 'error');
        return;
    }
    
    // Обновляем заголовок
    const title = document.getElementById('addQuestionModalTitle');
    if (title) title.textContent = 'Редактировать вопрос';
    
    modal.classList.add('active');
    
    // Заполняем категорию
    const categorySelect = document.getElementById('addQuestionCategory');
    if (categorySelect) {
        categorySelect.innerHTML = '<option value="">Выберите категорию</option>';
        allCategories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat.name;
            option.textContent = cat.name;
            option.selected = cat.name === actualCategory;
            categorySelect.appendChild(option);
        });
    }
    
    // Заполняем форму
    const questionTextInput = document.getElementById('addQuestionText');
    const explanationInput = document.getElementById('addExplanation');
    const difficultySelect = document.getElementById('addDifficulty');
    
    if (questionTextInput) questionTextInput.value = question.question || '';
    if (explanationInput) explanationInput.value = question.explanation || '';
    if (difficultySelect) difficultySelect.value = question.difficulty || 'medium';
    
    // Заполняем варианты ответов
    const optionsContainer = document.getElementById('addQuestionOptionsContainer');
    if (!optionsContainer) {
        console.error('addQuestionOptionsContainer not found in editQuestion!');
        showToast('Контейнер вариантов ответов не найден', 'error');
        return;
    }
    
    // Получаем варианты ответов - если их нет, загружаем вопрос из API
    let options = question.options || question.answers || [];
    if (!Array.isArray(options) || options.length === 0) {
        console.warn('Question has no options in allQuestions, loading from API...', {
            question: question.question?.substring(0, 50),
            hasOptions: !!question.options,
            hasAnswers: !!question.answers,
            options: question.options,
            answers: question.answers
        });
        
        // Загружаем вопрос напрямую из API категории
        try {
            const response = await fetch(`/api/categories/${encodeURIComponent(actualCategory)}/questions/${actualIndex}`);
            if (response.ok) {
                const data = await response.json();
                const fullQuestion = data.question;
                options = fullQuestion.options || fullQuestion.answers || [];
                question.correct = fullQuestion.correct || fullQuestion.correct_answer || question.correct;
                question.explanation = fullQuestion.explanation || question.explanation;
                question.difficulty = fullQuestion.difficulty || question.difficulty;
                
                // Обновляем поля формы
                if (explanationInput) explanationInput.value = question.explanation || '';
                if (difficultySelect) difficultySelect.value = question.difficulty || 'medium';
                
                console.log('Question loaded from API:', {
                    optionsCount: options.length,
                    options: options,
                    correct: question.correct
                });
            } else {
                console.error('Failed to load question from API:', response.status);
            }
        } catch (error) {
            console.error('Error loading question from API:', error);
        }
    }
    
    if (!Array.isArray(options)) {
        options = [];
    }
    
    console.log('Loading question options:', {
        question: question.question?.substring(0, 50),
        optionsCount: options.length,
        options: options,
        correct: question.correct || question.correct_answer
    });
    
    // Очищаем контейнер
    optionsContainer.innerHTML = '';
    
    // Добавляем варианты ответов
    if (options.length > 0) {
        options.forEach((opt) => {
            // Убеждаемся, что opt - это строка
            const optValue = typeof opt === 'string' ? opt : String(opt || '');
            addOptionInput(optionsContainer, optValue, false);
        });
    } else {
        // Если вариантов нет, добавляем 2 пустых
        console.warn('Question has no options, adding empty fields');
        addOptionInput(optionsContainer, '', false);
        addOptionInput(optionsContainer, '', false);
    }
    
    // Устанавливаем правильный ответ после того, как варианты добавлены
    // Используем несколько попыток, чтобы убедиться, что select обновился
    const updateCorrectAnswer = () => {
        const correctAnswerSelect = document.getElementById('addCorrectAnswer');
        if (!correctAnswerSelect) {
            console.error('addCorrectAnswer select not found!');
            return;
        }
        
        const correctValue = question.correct || question.correct_answer || '';
        console.log('Setting correct answer:', correctValue, 'available options:', Array.from(correctAnswerSelect.options).map(o => o.value));
        
        if (correctValue) {
            // Проверяем, есть ли такой вариант в select
            const optionExists = Array.from(correctAnswerSelect.options).some(opt => opt.value === correctValue);
            if (optionExists) {
                correctAnswerSelect.value = correctValue;
                console.log('Correct answer set to:', correctAnswerSelect.value);
            } else {
                console.warn('Correct answer value not found in select options:', correctValue);
                // Пробуем еще раз через небольшую задержку
                setTimeout(updateCorrectAnswer, 100);
            }
        }
    };
    
    // Первая попытка сразу
    setTimeout(updateCorrectAnswer, 50);
    // Вторая попытка через 200мс на случай, если select еще не обновился
    setTimeout(updateCorrectAnswer, 200);
}

async function deleteQuestion(category, index) {
    if (!confirm(`Удалить вопрос из категории "${category}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/categories/${encodeURIComponent(category)}/questions/${index}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Вопрос удален', 'success');
            loadQuestions(); // Перезагружаем список
        } else {
            const result = await response.json();
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error deleting question:', error);
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        
        // Очищаем форму если это модалка вопросов
        if (modalId === 'addQuestionModal') {
            const form = modal.querySelector('form');
            if (form) form.reset();
            
            // Очищаем варианты ответов
            const optionsContainer = document.getElementById('addQuestionOptionsContainer');
            if (optionsContainer) {
                optionsContainer.innerHTML = '';
            }
            
            // Очищаем select правильного ответа
            const correctAnswerSelect = document.getElementById('addCorrectAnswer');
            if (correctAnswerSelect) {
                correctAnswerSelect.innerHTML = '<option value="">Выберите правильный ответ</option>';
            }
            
            currentEditingQuestion = null;
        }
    }
}

function addOptionInput(container, value = '', isCorrect = false) {
    if (!container) {
        console.error('Container not found for addOptionInput');
        return;
    }
    
    const div = document.createElement('div');
    div.className = 'dynamic-list-item';
    div.style.cssText = 'display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; padding: 0.375rem; background: var(--bg-primary); border-radius: 6px; border: 1px solid var(--border-color);';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-input option-input';
    input.value = value; // Не используем escapeHtml для значения input
    input.placeholder = 'Вариант ответа';
    input.style.cssText = 'flex: 1; padding: 0.5rem; font-size: 0.875rem;';
    input.addEventListener('input', updateCorrectAnswerSelect);
    
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn-remove';
    removeBtn.textContent = '×';
    removeBtn.style.cssText = 'background: var(--danger); color: white; border: none; border-radius: 50%; width: 28px; height: 28px; cursor: pointer; font-size: 1.2rem; line-height: 1; display: flex; align-items: center; justify-content: center; flex-shrink: 0;';
    removeBtn.addEventListener('click', () => removeOptionInput(removeBtn));
    
    div.appendChild(input);
    div.appendChild(removeBtn);
    container.appendChild(div);
    
    // Обновляем select правильного ответа
    updateCorrectAnswerSelect();
    
    console.log('Option input added, container now has', container.children.length, 'children');
}

function removeOptionInput(button) {
    button.parentElement.remove();
    updateCorrectAnswerSelect();
}

function updateCorrectAnswerSelect() {
    const container = document.getElementById('addQuestionOptionsContainer');
    const select = document.getElementById('addCorrectAnswer');
    if (!container || !select) {
        console.warn('updateCorrectAnswerSelect: container or select not found');
        return;
    }
    
    const options = Array.from(container.querySelectorAll('.option-input'))
        .map(input => input.value.trim())
        .filter(val => val);
    
    // Сохраняем текущее значение, если оно есть
    const currentValue = select.value;
    
    // Обновляем select с вариантами
    select.innerHTML = '<option value="">Выберите правильный ответ</option>' + 
        options.map((opt, idx) => 
            `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`
        ).join('');
    
    // Восстанавливаем значение, если оно все еще существует в списке
    if (currentValue && options.includes(currentValue)) {
        select.value = currentValue;
    } else if (options.length > 0 && !currentValue) {
        // Если значения не было, не меняем select (оставляем пустым)
        // Это важно при редактировании, чтобы не сбрасывать правильный ответ
    }
    
    console.log('updateCorrectAnswerSelect: updated with', options.length, 'options, current value:', select.value);
}

// ========== Chats Management ==========
async function loadChats() {
    const container = document.getElementById('chatsContainer');
    if (container) {
        container.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка чатов...</p>';
    }
    
    try {
        const response = await fetch('/api/chats');
        allChats = await response.json();
        renderChats();
        showToast(`Загружено ${allChats.length} чатов`, 'success');
    } catch (error) {
        console.error('Error loading chats:', error);
        if (container) {
            container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem;">Ошибка загрузки: ${error.message}</p>`;
        }
        showToast('Ошибка загрузки чатов', 'error');
    }
}

function renderChats() {
    const container = document.getElementById('chatsContainer');
    
    if (!allChats || allChats.length === 0) {
        container.innerHTML = `
            <div class="card" style="text-align: center; padding: 3rem;">
                <div style="font-size: 4rem; margin-bottom: 1rem;">💬</div>
                <h3 style="margin-bottom: 1rem;">Нет подключенных чатов</h3>
                <p style="color: var(--text-secondary);">Добавьте бота в чат для начала работы</p>
            </div>
        `;
        return;
    }
    
    // Статистика по чатам
    const groupChats = allChats.filter(c => String(c.id).startsWith('-'));
    const privateChats = allChats.filter(c => !String(c.id).startsWith('-'));
    const activeChats = allChats.filter(c => c.daily_quiz_enabled);
    
    container.innerHTML = `
        <!-- Статистика -->
        <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
            <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                <span style="font-size: 1.5rem; font-weight: 700; color: var(--primary);">${allChats.length}</span>
                <span style="color: var(--text-secondary); margin-left: 0.5rem;">Всего чатов</span>
            </div>
            <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                <span style="font-size: 1.5rem; font-weight: 700; color: var(--info);">${groupChats.length}</span>
                <span style="color: var(--text-secondary); margin-left: 0.5rem;">Групп</span>
            </div>
            <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                <span style="font-size: 1.5rem; font-weight: 700; color: var(--secondary);">${privateChats.length}</span>
                <span style="color: var(--text-secondary); margin-left: 0.5rem;">Личных</span>
            </div>
            <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                <span style="font-size: 1.5rem; font-weight: 700; color: var(--success);">${activeChats.length}</span>
                <span style="color: var(--text-secondary); margin-left: 0.5rem;">С подпиской</span>
            </div>
        </div>
        
        <!-- Список чатов -->
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1rem;">
            ${allChats.map(chat => {
                const isGroup = String(chat.id).startsWith('-');
                return `
                <div class="card" style="padding: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                        <div style="flex: 1; min-width: 0;">
                                <div style="display: flex; align-items: center; gap: 0.5rem;">
                                    <span style="font-size: 1.25rem;">${isGroup ? '👥' : '👤'}</span>
                                    <h3 style="margin: 0; font-size: 1rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${chat.title || 'Чат ' + chat.id}">
                                        ${chat.title || 'Чат ' + chat.id}
                            </h3>
                        </div>
                                <p style="color: var(--text-secondary); font-size: 0.75rem; margin: 0.25rem 0 0 2rem;">ID: ${chat.id}</p>
                            </div>
                            <span class="badge" style="background: ${chat.daily_quiz_enabled ? 'var(--success)' : 'var(--gray-400)'}; color: white; font-size: 0.7rem; padding: 0.25rem 0.5rem;">
                                ${chat.daily_quiz_enabled ? '✓ Активен' : '○ Неактив'}
                        </span>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-bottom: 0.75rem;">
                            <div style="background: var(--bg-secondary); padding: 0.5rem; border-radius: 6px; text-align: center;">
                            <div style="font-size: 1.25rem; font-weight: 700; color: var(--primary);">${chat.users_count || 0}</div>
                                <div style="font-size: 0.7rem; color: var(--text-secondary);">Пользователей</div>
                        </div>
                            <div style="background: var(--bg-secondary); padding: 0.5rem; border-radius: 6px; text-align: center;">
                            <div style="font-size: 1.25rem; font-weight: 700; color: var(--success);">${chat.total_quizzes || 0}</div>
                                <div style="font-size: 0.7rem; color: var(--text-secondary);">Викторин</div>
                        </div>
                            <div style="background: var(--bg-secondary); padding: 0.5rem; border-radius: 6px; text-align: center;">
                                <div style="font-size: 1.25rem; font-weight: 700; color: var(--warning);">${(chat.daily_quiz_times || []).length}</div>
                                <div style="font-size: 0.7rem; color: var(--text-secondary);">Расписаний</div>
                        </div>
                    </div>
                    
                    ${chat.daily_quiz_enabled && chat.daily_quiz_times && chat.daily_quiz_times.length > 0 ? `
                            <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">⏰ Время запуска (МСК):</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 0.375rem;">
                                ${chat.daily_quiz_times.map(t => 
                                    `<span style="background: var(--primary); color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">${String(t.hour).padStart(2, '0')}:${String(t.minute).padStart(2, '0')}</span>`
                                ).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem;">
                            <button class="btn btn-secondary btn-sm" onclick="viewChatStats('${chat.id}')" style="font-size: 0.75rem; padding: 0.4rem;">
                                📊 Стат.
                        </button>
                            <button class="btn btn-primary btn-sm" onclick="editChatSchedule('${chat.id}')" style="font-size: 0.75rem; padding: 0.4rem;">
                                ⚙️ Настр.
                            </button>
                            <button class="btn ${chat.daily_quiz_enabled ? 'btn-danger' : 'btn-success'} btn-sm"
                                    onclick="toggleChatEnabled('${chat.id}', ${!chat.daily_quiz_enabled})" style="font-size: 0.75rem; padding: 0.4rem;">
                                ${chat.daily_quiz_enabled ? '⏸️ Выкл.' : '▶️ Вкл.'}
                        </button>
                    </div>
                </div>
                `;
            }).join('')}
        </div>
    `;
}

async function toggleChatEnabled(chatId, enabled) {
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/subscription/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(enabled ? '✅ Подписка включена' : '⏸️ Подписка выключена', 'success');
            loadChats();
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error toggling chat subscription:', error);
    }
}

function editChatSchedule(chatId) {
    // Находим чат
    const chat = allChats.find(c => String(c.id) === String(chatId));
    if (!chat) {
        showToast('Чат не найден', 'error');
        return;
    }
    
    // Открываем модальное окно для редактирования расписания
    const modal = document.getElementById('chatScheduleModal');
    if (!modal) {
        showToast('Модальное окно не найдено', 'error');
        return;
    }
    
    // Сохраняем chatId для сохранения (как строку)
    modal.dataset.chatId = String(chatId);
    
    // Обновляем заголовок модалки
    const modalTitle = modal.querySelector('.modal-title');
    if (modalTitle) {
        modalTitle.textContent = `⚙️ Настройка: ${chat.title || 'Чат ' + chatId}`;
    }
    
    // Заполняем форму
    document.getElementById('editDailyQuizEnabled').checked = chat.daily_quiz_enabled || false;
    
    // Заполняем расписание
    const timesContainer = document.getElementById('dailyQuizTimesContainer');
    if (timesContainer) {
        timesContainer.innerHTML = '';
        const times = chat.daily_quiz_times || [];
        if (times.length > 0) {
            times.forEach(time => {
                addDailyQuizTime(time.hour, time.minute);
            });
        } else {
            addDailyQuizTime(9, 0); // По умолчанию 9:00
        }
    }
    
    modal.classList.add('active');
}

async function saveChatSchedule() {
    const modal = document.getElementById('chatScheduleModal');
    if (!modal) return;
    
    const chatId = modal.dataset.chatId;
    if (!chatId) {
        showToast('ID чата не найден', 'error');
        return;
    }
    
    const enabled = document.getElementById('editDailyQuizEnabled').checked;
    
    // Собираем времена
    const times = [];
    const timeItems = modal.querySelectorAll('.daily-quiz-time-item');
    timeItems.forEach(item => {
        const hour = parseInt(item.querySelector('.time-hour').value);
        const minute = parseInt(item.querySelector('.time-minute').value);
        if (!isNaN(hour) && !isNaN(minute) && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59) {
            times.push({ hour, minute });
        }
    });
    
    if (enabled && times.length === 0) {
        showToast('Добавьте хотя бы одно время для расписания', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/subscription`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled: enabled,
                times_msk: times
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast('✅ Расписание обновлено', 'success');
            closeModal('chatScheduleModal');
            loadChats();
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error saving chat schedule:', error);
    }
}

function addDailyQuizTime(hour = 9, minute = 0) {
    const container = document.getElementById('dailyQuizTimesContainer');
    if (!container) return;
    
    const div = document.createElement('div');
    div.className = 'daily-quiz-time-item';
    div.style.cssText = 'display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;';
    div.innerHTML = `
        <input type="number" class="form-input time-hour" min="0" max="23" value="${hour}" style="width: 70px;" placeholder="Час">
        <span>:</span>
        <input type="number" class="form-input time-minute" min="0" max="59" value="${minute}" style="width: 70px;" placeholder="Мин">
        <button type="button" class="btn-remove" onclick="removeDailyQuizTime(this)" style="background: var(--danger); color: white; border: none; border-radius: 50%; width: 28px; height: 28px; cursor: pointer;">×</button>
    `;
    container.appendChild(div);
}

function removeDailyQuizTime(button) {
    button.parentElement.remove();
}

// ========== Other Sections ==========
async function loadPhotoQuiz() {
    const container = document.getElementById('photoQuizContainer');
    if (!container) return;
    
    container.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка фото-викторин...</p>';
    
    try {
        const response = await fetch('/api/photo-quiz');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Ошибка загрузки');
        }
        
        const photos = data.photos || [];
        
        if (photos.length === 0) {
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 3rem;">
                    <div style="font-size: 4rem; margin-bottom: 1rem;">🖼️</div>
                    <h3 style="margin-bottom: 1rem;">Нет фото-викторин</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Создайте первую фото-викторину</p>
                    <button class="btn btn-primary" onclick="addNewPhotoQuiz()">➕ Добавить фото-викторину</button>
                </div>
            `;
            return;
        }
        
        // Статистика
        const withImages = photos.filter(p => p.has_image).length;
        
        container.innerHTML = `
            <!-- Статистика -->
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--primary);">${photos.length}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Всего</span>
                </div>
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--success);">${withImages}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">С изображениями</span>
                </div>
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--warning);">${photos.length - withImages}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Без изображений</span>
                </div>
            </div>
            
            <!-- Галерея -->
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem;">
                ${photos.map(photo => `
                    <div class="card" style="padding: 0; overflow: hidden;">
                        ${photo.has_image && photo.image_url ? `
                            <div style="height: 150px; background-image: url('${photo.image_url}'); background-size: cover; background-position: center; cursor: pointer;" onclick="viewPhotoFullSize('${photo.image_url}', '${escapeHtml(photo.name)}')"></div>
                        ` : `
                            <div style="height: 150px; background: var(--bg-secondary); display: flex; align-items: center; justify-content: center; color: var(--text-secondary);">
                                <span style="font-size: 3rem;">🖼️</span>
                                </div>
                        `}
                        <div style="padding: 1rem;">
                            <div style="font-weight: 600; margin-bottom: 0.25rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(photo.name)}">${escapeHtml(photo.name)}</div>
                            <div style="color: var(--success); font-size: 0.875rem; font-weight: 500; margin-bottom: 0.75rem;">${escapeHtml(photo.correct_answer || 'Ответ не указан')}</div>
                            <div style="display: flex; gap: 0.5rem;">
                                <button class="btn btn-sm btn-secondary" onclick="editPhotoQuiz('${escapeHtml(photo.name)}')" style="flex: 1;">✏️ Изменить</button>
                            <button class="btn btn-sm btn-danger" onclick="deletePhotoQuiz('${escapeHtml(photo.name)}')" title="Удалить">🗑️</button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        showToast(`Загружено ${photos.length} фото-викторин`, 'success');
    } catch (error) {
        console.error('Error loading photo quiz:', error);
        container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem;">Ошибка загрузки: ${escapeHtml(error.message)}</p>`;
        showToast('Ошибка загрузки фото-викторин', 'error');
    }
}

function editPhotoQuiz(name) {
    // Загружаем данные photo quiz
    fetch('/api/photo-quiz')
        .then(r => r.json())
        .then(data => {
            const photos = data.photos || [];
            const photo = photos.find(p => p.name === name);
            
            if (!photo) {
                showToast('Фото-викторина не найдена', 'error');
                return;
            }
            
            const modalHtml = `
                <div class="modal-overlay active" id="editPhotoModal" onclick="if(event.target.id === 'editPhotoModal') closeModal('editPhotoModal')">
                    <div class="modal-content" onclick="event.stopPropagation()">
                        <div class="modal-header">
                            <h3 class="modal-title">✏️ Редактировать фото-викторину</h3>
                            <button class="modal-close-btn" onclick="closeModal('editPhotoModal')">×</button>
                        </div>
                        <div class="modal-body">
                            ${photo.has_image && photo.image_url ? `
                                <div style="text-align: center; margin-bottom: 1rem;">
                                    <img src="${photo.image_url}" style="max-width: 100%; max-height: 200px; border-radius: 8px;" alt="${escapeHtml(name)}">
                                </div>
                            ` : ''}
                            
                            <div class="form-group">
                                <label class="form-label">Название</label>
                                <input type="text" class="form-input" id="editPhotoName" value="${escapeHtml(name)}" readonly style="background: var(--bg-secondary);">
                            </div>
                            
                            <div class="form-group">
                                <label class="form-label">Правильный ответ *</label>
                                <input type="text" class="form-input" id="editPhotoAnswer" value="${escapeHtml(photo.correct_answer || '')}" required>
                            </div>
                            
                            <div class="form-group">
                                <label class="form-label">Подсказки</label>
                                <div style="background: var(--bg-secondary); padding: 0.75rem; border-radius: 8px; font-size: 0.875rem;">
                                    ${photo.hints ? Object.entries(photo.hints).map(([key, val]) => 
                                        `<div style="margin-bottom: 0.25rem;"><strong>${escapeHtml(key)}:</strong> ${escapeHtml(String(val))}</div>`
                                    ).join('') : 'Нет подсказок'}
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-secondary" onclick="closeModal('editPhotoModal')">Отмена</button>
                            <button class="btn btn-primary" onclick="savePhotoQuiz('${escapeHtml(name)}')">Сохранить</button>
                        </div>
                    </div>
                </div>
            `;
            
            // Удаляем старую модалку если есть
            const oldModal = document.getElementById('editPhotoModal');
            if (oldModal) oldModal.remove();
            
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        })
        .catch(error => {
            showToast(`Ошибка: ${error.message}`, 'error');
        });
}

async function savePhotoQuiz(name) {
    const correctAnswer = document.getElementById('editPhotoAnswer')?.value;
    
    if (!correctAnswer || !correctAnswer.trim()) {
        showToast('Введите правильный ответ', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/photo-quiz/${encodeURIComponent(name)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                correct_answer: correctAnswer.trim(),
                hints: {
                    length: correctAnswer.length,
                    first_letter: correctAnswer[0],
                    partial: correctAnswer[0] + '_'.repeat(Math.max(0, correctAnswer.length - 1))
                }
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast('Фото-викторина обновлена', 'success');
            closeModal('editPhotoModal');
            loadPhotoQuiz();
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
    }
}

async function deletePhotoQuiz(name) {
    if (!confirm(`Удалить фото-викторину "${name}"?\n\nЭто действие также удалит изображение.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/photo-quiz/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast('Фото-викторина удалена', 'success');
            loadPhotoQuiz();
        } else {
            showToast(`Ошибка: ${result.detail || 'Неизвестная ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
        console.error('Error deleting photo quiz:', error);
    }
}

function addNewPhotoQuiz() {
    const modalHtml = `
        <div class="modal-overlay active" id="addPhotoModal" onclick="if(event.target.id === 'addPhotoModal') closeModal('addPhotoModal')">
            <div class="modal-content" onclick="event.stopPropagation()" style="max-width: 600px;">
                <div class="modal-header">
                    <h3 class="modal-title">➕ Добавить фото-викторину</h3>
                    <button class="modal-close-btn" onclick="closeModal('addPhotoModal')">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Название (ID) *</label>
                        <input type="text" class="form-input" id="newPhotoName" placeholder="Уникальное название латиницей" required>
                        <p class="form-hint">Например: MyQuiz1 или CatPicture</p>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Изображение *</label>
                        <div class="file-upload-area" id="newPhotoFileUploadArea" style="border: 2px dashed var(--border-color); border-radius: 8px; padding: 2rem; text-align: center; cursor: pointer; transition: all 0.3s; background: var(--bg-secondary);" onmouseover="this.style.borderColor='var(--primary)'; this.style.background='var(--bg-primary)'" onmouseout="this.style.borderColor='var(--border-color)'; this.style.background='var(--bg-secondary)'">
                            <div style="font-size: 2rem; margin-bottom: 0.5rem;">📁</div>
                            <div style="font-weight: 600; margin-bottom: 0.25rem;">Нажмите для выбора файла</div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary);">или перетащите изображение сюда</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">Поддерживаемые форматы: JPG, PNG, GIF, WEBP</div>
                            <input type="file" id="newPhotoFile" accept="image/*" style="display: none;">
                        </div>
                        <div id="newPhotoPreview" style="margin-top: 1rem; display: none;">
                            <div style="position: relative; display: inline-block;">
                                <img id="newPhotoPreviewImg" src="" style="max-width: 100%; max-height: 300px; border-radius: 8px; border: 1px solid var(--border-color);">
                                <button type="button" onclick="clearPhotoPreview()" style="position: absolute; top: 0.5rem; right: 0.5rem; background: var(--danger); color: white; border: none; border-radius: 50%; width: 2rem; height: 2rem; cursor: pointer; font-size: 1.2rem; line-height: 1;">×</button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Правильный ответ *</label>
                        <input type="text" class="form-input" id="newPhotoAnswer" placeholder="Ответ на викторину" required>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('addPhotoModal')">Отмена</button>
                    <button class="btn btn-primary" onclick="createPhotoQuiz()">Создать</button>
                </div>
            </div>
        </div>
    `;
    
    // Удаляем старую модалку если есть
    const oldModal = document.getElementById('addPhotoModal');
    if (oldModal) oldModal.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Настраиваем загрузку файла
    setupNewPhotoFileUpload();
}

function setupNewPhotoFileUpload() {
    const area = document.getElementById('newPhotoFileUploadArea');
    const input = document.getElementById('newPhotoFile');
    const preview = document.getElementById('newPhotoPreview');
    const previewImg = document.getElementById('newPhotoPreviewImg');
    
    if (!area || !input) return;
    
    // Клик по области
    area.addEventListener('click', () => input.click());
    
    // Изменение файла
    input.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            if (!file.type.startsWith('image/')) {
                showToast('Выберите файл изображения', 'error');
                return;
            }
            showNewPhotoPreview(file);
        }
    });
    
    // Drag and drop
    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.style.borderColor = 'var(--primary)';
        area.style.background = 'var(--bg-primary)';
    });
    
    area.addEventListener('dragleave', () => {
        area.style.borderColor = 'var(--border-color)';
        area.style.background = 'var(--bg-secondary)';
    });
    
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.style.borderColor = 'var(--border-color)';
        area.style.background = 'var(--bg-secondary)';
        
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            input.files = e.dataTransfer.files;
            showNewPhotoPreview(file);
        } else {
            showToast('Перетащите файл изображения', 'error');
        }
    });
}

function showNewPhotoPreview(file) {
    const preview = document.getElementById('newPhotoPreview');
    const previewImg = document.getElementById('newPhotoPreviewImg');
    
    if (!preview || !previewImg) return;
    
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function clearPhotoPreview() {
    const input = document.getElementById('newPhotoFile');
    const preview = document.getElementById('newPhotoPreview');
    
    if (input) input.value = '';
    if (preview) preview.style.display = 'none';
}

async function createPhotoQuiz() {
    const name = document.getElementById('newPhotoName')?.value;
    const correctAnswer = document.getElementById('newPhotoAnswer')?.value;
    const fileInput = document.getElementById('newPhotoFile');
    const file = fileInput?.files[0];
    
    if (!name || !name.trim()) {
        showToast('Введите название', 'error');
        return;
    }
    
    if (!correctAnswer || !correctAnswer.trim()) {
        showToast('Введите правильный ответ', 'error');
        return;
    }
    
    if (!file) {
        showToast('Выберите изображение', 'error');
        return;
    }
    
    try {
        // Сначала создаем запись фото-викторины
        const createResponse = await fetch(`/api/photo-quiz?name=${encodeURIComponent(name.trim())}&correct_answer=${encodeURIComponent(correctAnswer.trim())}`, {
            method: 'POST'
        });
        
        const createResult = await createResponse.json();
        
        if (!createResponse.ok) {
            showToast(`Ошибка: ${createResult.detail || 'Неизвестная ошибка'}`, 'error');
            return;
        }
        
        // Затем загружаем изображение
        const formData = new FormData();
        formData.append('file', file);
        
        const uploadResponse = await fetch(`/api/photo-quiz/${encodeURIComponent(name.trim())}/upload-image`, {
            method: 'POST',
            body: formData
        });
        
        const uploadResult = await uploadResponse.json();
        
        if (!uploadResponse.ok) {
            // Если загрузка изображения не удалась, удаляем созданную запись
            await fetch(`/api/photo-quiz/${encodeURIComponent(name.trim())}`, {
                method: 'DELETE'
            });
            showToast(`Ошибка загрузки изображения: ${uploadResult.detail || 'Неизвестная ошибка'}`, 'error');
            return;
        }
        
        showToast('Фото-викторина создана и изображение загружено', 'success');
        closeModal('addPhotoModal');
        loadPhotoQuiz();
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
    }
}

function viewPhotoFullSize(imageUrl, name) {
    const modalHtml = `
        <div class="modal-overlay active" id="viewPhotoModal" onclick="closeModal('viewPhotoModal')" style="padding: 2rem;">
            <div style="max-width: 90vw; max-height: 90vh; text-align: center;">
                <img src="${imageUrl}" style="max-width: 100%; max-height: 80vh; border-radius: 8px; box-shadow: 0 20px 60px rgba(0,0,0,0.5);" alt="${escapeHtml(name)}">
                <div style="color: white; margin-top: 1rem; font-size: 1.25rem; font-weight: 600;">${escapeHtml(name)}</div>
            </div>
        </div>
    `;
    
    const oldModal = document.getElementById('viewPhotoModal');
    if (oldModal) oldModal.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

async function loadAnalytics() {
    const container = document.getElementById('analyticsContainer');
    if (!container) return;
    
    container.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка аналитики...</p>';
    
    try {
        const response = await fetch('/api/analytics/summary');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Ошибка загрузки');
        }
        
        const overview = data.overview || {};
        const topUsers = data.top_users || [];
        const topCategories = data.top_categories || [];
        const chats = data.chats || [];
        
        container.innerHTML = `
            <!-- Overview Stats -->
            <div class="kpi-grid" style="margin-bottom: 2rem;">
                <div class="kpi-card">
                    <div class="kpi-header">
                        <div>
                            <div class="kpi-label">Пользователей</div>
                            <div class="kpi-value">${overview.total_users || 0}</div>
                        </div>
                        <div class="kpi-icon primary">👥</div>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-header">
                        <div>
                            <div class="kpi-label">Всего ответов</div>
                            <div class="kpi-value">${overview.total_answered || 0}</div>
                        </div>
                        <div class="kpi-icon success">✅</div>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-header">
                        <div>
                            <div class="kpi-label">Общий счёт</div>
                            <div class="kpi-value">${overview.total_score || 0}</div>
                        </div>
                        <div class="kpi-icon warning">🏆</div>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-header">
                        <div>
                            <div class="kpi-label">Чатов</div>
                            <div class="kpi-value">${overview.total_chats || 0}</div>
                        </div>
                        <div class="kpi-icon info">💬</div>
                    </div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <!-- Рейтинг пользователей -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
                        🏆 Рейтинг пользователей
                        <button class="btn btn-sm btn-secondary" onclick="exportLeaderboard()">📥 Экспорт</button>
                    </h3>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th style="width: 50px;">#</th>
                                    <th>Имя</th>
                                    <th style="text-align: right;">Баллы</th>
                                    <th style="text-align: right;">Ответов</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${topUsers.map((user, idx) => `
                                    <tr style="cursor: pointer;" onclick="viewUserStats('${user.user_id}')" title="Нажмите для просмотра деталей">
                                        <td>
                                            <span style="display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; background: ${idx < 3 ? ['#fbbf24', '#9ca3af', '#cd7f32'][idx] : 'var(--bg-secondary)'}; color: ${idx < 3 ? 'white' : 'var(--text-primary)'}; font-weight: 600; font-size: 0.8rem;">
                                                ${idx + 1}
                                            </span>
                                        </td>
                                        <td style="font-weight: 500;">${escapeHtml(user.name)}</td>
                                        <td style="text-align: right; font-weight: 700; color: var(--success);">${user.score}</td>
                                        <td style="text-align: right; color: var(--text-secondary);">${user.answered}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
                
                <!-- Статистика чатов -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem;">💬 Активность чатов</h3>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Чат</th>
                                    <th style="text-align: center;">👥</th>
                                    <th style="text-align: right;">Ответов</th>
                                    <th style="text-align: right;">Баллы</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${chats.map(chat => `
                                    <tr style="cursor: pointer;" onclick="viewChatStats('${chat.chat_id}')">
                                        <td>
                                            <div style="font-weight: 500;">${escapeHtml(chat.title)}</div>
                                            <div style="font-size: 0.75rem; color: var(--text-secondary);">${chat.chat_id}</div>
                                        </td>
                                        <td style="text-align: center;">${chat.users}</td>
                                        <td style="text-align: right; font-weight: 600;">${chat.answered}</td>
                                        <td style="text-align: right; color: var(--success);">${chat.score}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Топ категорий -->
            <div class="card" style="margin-top: 1.5rem;">
                <h3 style="margin-bottom: 1rem;">📚 Топ категорий по количеству вопросов</h3>
                <div style="display: flex; flex-wrap: wrap; gap: 0.75rem;">
                    ${topCategories.map((cat, idx) => `
                        <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                            <span style="font-weight: 600; color: var(--primary);">${idx + 1}.</span>
                            <span>${escapeHtml(cat.name)}</span>
                            <span class="badge" style="background: var(--primary);">${cat.questions}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        showToast('Аналитика загружена', 'success');
    } catch (error) {
        console.error('Error loading analytics:', error);
        container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem;">Ошибка загрузки: ${escapeHtml(error.message)}</p>`;
        showToast('Ошибка загрузки аналитики', 'error');
    }
}

async function viewChatStats(chatId) {
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/full`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Ошибка загрузки');
        }
        
        const users = data.users || [];
        const stats = data.stats || {};
        const settings = data.settings || {};
        const categoriesStats = data.categories_stats || [];
        const dailyQuiz = data.daily_quiz_config || {};
        
        // Форматирование даты
        const formatDate = (dateStr) => {
            if (!dateStr) return '—';
            try {
                const d = new Date(dateStr);
                return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            } catch { return '—'; }
        };
        
        const modalHtml = `
            <div class="modal-overlay active" id="chatStatsModal" onclick="if(event.target.id === 'chatStatsModal') closeModal('chatStatsModal')">
                <div class="modal-content" style="max-width: 900px; max-height: 90vh;" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3 class="modal-title">📊 ${escapeHtml(data.title || 'Чат ' + chatId)}</h3>
                        <button class="modal-close-btn" onclick="closeModal('chatStatsModal')">×</button>
                    </div>
                    <div class="modal-body" style="overflow-y: auto; max-height: calc(90vh - 130px);">
                        <!-- Метаданные чата -->
                        <div style="display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                            <div><strong>ID:</strong> ${chatId}</div>
                            <div><strong>Тип:</strong> ${data.type === 'group' ? '👥 Группа' : data.type === 'supergroup' ? '👥 Супергруппа' : '👤 Личный'}</div>
                            <div><strong>Дата миграции:</strong> ${formatDate(data.migration_date)}</div>
                        </div>
                        
                        <!-- KPI -->
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.5rem;">
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--primary);">${stats.total_users || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Пользователей</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--success);">${stats.total_answered || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Ответов</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--warning);">${stats.total_score || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Баллов</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--info);">${dailyQuiz.enabled ? '✓' : '✗'}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Подписка</div>
                            </div>
                        </div>
                        
                        <!-- Настройки ежедневных викторин -->
                        ${dailyQuiz.enabled ? `
                            <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <h4 style="margin: 0 0 0.5rem; font-size: 0.9rem;">⏰ Расписание викторин (МСК)</h4>
                                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                                    ${(dailyQuiz.times_msk || []).map(t => `
                                        <span style="background: var(--primary); color: white; padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.875rem; font-weight: 600;">
                                            ${String(t.hour).padStart(2, '0')}:${String(t.minute).padStart(2, '0')}
                                        </span>
                                    `).join('')}
                                </div>
                                <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--text-secondary);">
                                    Вопросов: ${dailyQuiz.num_questions || 10} | Интервал: ${dailyQuiz.interval_seconds || 60}с | Время на ответ: ${dailyQuiz.poll_open_seconds || 600}с
                                </div>
                            </div>
                        ` : ''}
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                            <!-- Рейтинг пользователей -->
                            <div>
                                <h4 style="margin-bottom: 0.75rem;">🏆 Рейтинг пользователей (${users.length})</h4>
                                <div style="max-height: 350px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px;">
                                    <table class="data-table" style="margin: 0;">
                                        <thead style="position: sticky; top: 0; background: var(--bg-secondary);">
                                            <tr>
                                                <th style="width: 30px;">#</th>
                                                <th>Имя</th>
                                                <th style="text-align: right;">Баллы</th>
                                                <th style="text-align: right;">Отв.</th>
                                                <th style="text-align: right;">🔥</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${users.map(user => `
                                                <tr style="cursor: pointer;" onclick="viewUserStats('${user.user_id}')">
                                                    <td><strong>${user.rank}</strong></td>
                                                    <td style="max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(user.name)}">${escapeHtml(user.name)}</td>
                                                    <td style="text-align: right; font-weight: 600; color: var(--success);">${user.score}</td>
                                                    <td style="text-align: right;">${user.answered_count}</td>
                                                    <td style="text-align: right; color: var(--warning);">${user.max_consecutive_correct}</td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            
                            <!-- Статистика категорий -->
                            <div>
                                <h4 style="margin-bottom: 0.75rem;">📁 Категории и веса (${categoriesStats.length})</h4>
                                <div style="max-height: 350px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px;">
                                    <table class="data-table" style="margin: 0; font-size: 0.8rem;">
                                        <thead style="position: sticky; top: 0; background: var(--bg-secondary);">
                                            <tr>
                                                <th>Категория</th>
                                                <th style="text-align: right;">Исп.</th>
                                                <th style="text-align: right;">Вес</th>
                                                <th style="text-align: right;">Дней</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${categoriesStats.length > 0 ? categoriesStats.map(cat => {
                                                const usage = cat.chat_usage || cat.usage || 0;
                                                const weight = cat.weight !== undefined ? cat.weight : '—';
                                                const excluded = cat.excluded || false;
                                                const daysAgo = cat.days_since_use !== undefined ? cat.days_since_use : '—';
                                                const weightColor = excluded ? 'var(--danger)' : (weight > 50 ? 'var(--success)' : 'var(--warning)');

                                                return `
                                                <tr style="${excluded ? 'opacity: 0.6;' : ''}">
                                                    <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(cat.name)}">
                                                        ${escapeHtml(cat.name)} ${excluded ? '🚫' : ''}
                                                    </td>
                                                    <td style="text-align: right; font-weight: 600; color: var(--primary);">${usage}</td>
                                                    <td style="text-align: right; font-weight: 600; color: ${weightColor};">
                                                        ${typeof weight === 'number' ? weight.toFixed(1) : weight}
                                                    </td>
                                                    <td style="text-align: right; color: var(--text-secondary);">
                                                        ${typeof daysAgo === 'number' ? (daysAgo < 1 ? '<1' : Math.floor(daysAgo)) : daysAgo}
                                                    </td>
                                                </tr>
                                            `}).join('') : '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">Нет данных</td></tr>'}
                                        </tbody>
                                    </table>
                                </div>
                                <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);">
                                    🚫 - исключена (использована < 2 дней назад)
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer" style="justify-content: space-between;">
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn btn-secondary btn-sm" onclick="editChatTitle('${chatId}', '${escapeHtml(data.title || '')}')" title="Изменить название">
                                ✏️ Название
                            </button>
                            <button class="btn btn-warning btn-sm" onclick="resetChatStats('${chatId}')" title="Сбросить статистику">
                                🔄 Сбросить
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="banChat('${chatId}')" title="Заблокировать чат">
                                🚫 Бан
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="deleteChat('${chatId}')" title="Удалить чат">
                                🗑️ Удалить
                            </button>
                        </div>
                        <button class="btn btn-secondary" onclick="closeModal('chatStatsModal')">Закрыть</button>
                    </div>
                </div>
            </div>
        `;
        
        // Удаляем старые модалки если есть
        const oldModal = document.getElementById('chatStatsModal');
        if (oldModal) oldModal.remove();
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
    }
}

// Просмотр полной статистики пользователя
async function viewUserStats(userId) {
    try {
        const response = await fetch(`/api/users/${encodeURIComponent(userId)}`);
        const user = await response.json();
        
        if (!response.ok) {
            throw new Error(user.detail || 'Ошибка загрузки');
        }
        
        // Форматирование даты
        const formatDate = (dateStr) => {
            if (!dateStr) return '—';
            try {
                const d = new Date(dateStr);
                return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            } catch { return '—'; }
        };
        
        const chats = user.chats_activity || [];
        
        const modalHtml = `
            <div class="modal-overlay active" id="userStatsModal" onclick="if(event.target.id === 'userStatsModal') closeModal('userStatsModal')">
                <div class="modal-content" style="max-width: 800px; max-height: 90vh;" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3 class="modal-title">👤 ${escapeHtml(user.name || 'Пользователь ' + userId)}</h3>
                        <button class="modal-close-btn" onclick="closeModal('userStatsModal')">×</button>
                    </div>
                    <div class="modal-body" style="overflow-y: auto; max-height: calc(90vh - 130px);">
                        <!-- ID пользователя -->
                        <div style="margin-bottom: 1rem; padding: 0.5rem 1rem; background: var(--bg-secondary); border-radius: 8px;">
                            <strong>Telegram ID:</strong> <code style="background: var(--bg-tertiary); padding: 0.125rem 0.5rem; border-radius: 4px;">${userId}</code>
                        </div>
                        
                        <!-- KPI -->
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.5rem;">
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--success);">${user.total_score || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Всего баллов</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--primary);">${user.total_answered || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Ответов</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--warning);">🔥 ${user.max_streak || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Макс. серия</div>
                            </div>
                            <div style="text-align: center; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--info);">${user.chats_count || 0}</div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">Чатов</div>
                            </div>
                        </div>
                        
                        <!-- Даты активности -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem;">
                            <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">🕐 Первая активность</div>
                                <div style="font-weight: 600;">${formatDate(user.first_activity)}</div>
                            </div>
                            <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                                <div style="font-size: 0.75rem; color: var(--text-secondary);">🕐 Последняя активность</div>
                                <div style="font-weight: 600;">${formatDate(user.last_activity)}</div>
                            </div>
                        </div>
                        
                        <!-- Достижения (ачивки) -->
                        <div style="margin-bottom: 1.5rem;">
                            <h4 style="margin: 0 0 1rem; font-size: 1rem; display: flex; align-items: center; gap: 0.5rem;">
                                🏅 Достижения <span style="background: var(--primary); color: white; padding: 0.125rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 700;">${(user.achievements || []).length}</span>
                            </h4>
                            ${(user.achievements || []).length > 0 ? `
                                <div style="display: grid; gap: 0.5rem; max-height: 300px; overflow-y: auto; padding: 0.5rem;">
                                    ${user.achievements.map(ach => `
                                        <div style="display: flex; gap: 0.75rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; border-left: 3px solid ${
                                            ach.type === 'streak' ? 'var(--warning)' : 
                                            ach.type === 'chat' ? 'var(--success)' : 
                                            ach.type === 'motivational' ? 'var(--primary)' : 'var(--info)'
                                        };">
                                            <div style="font-size: 1.5rem;">${ach.icon}</div>
                                            <div style="flex: 1;">
                                                <div style="font-weight: 600; font-size: 0.875rem; margin-bottom: 0.125rem;">${escapeHtml(ach.title)}</div>
                                                <div style="font-size: 0.75rem; color: var(--text-secondary);">${escapeHtml(ach.description)}</div>
                                                ${ach.chat_title !== 'Глобальные' ? `<div style="font-size: 0.7rem; color: var(--text-tertiary); margin-top: 0.25rem;">📍 ${escapeHtml(ach.chat_title)}</div>` : ''}
                                            </div>
                                            <div style="align-self: center;">
                                                <span style="background: ${
                                                    ach.type === 'streak' ? 'var(--warning)' : 
                                                    ach.type === 'chat' ? 'var(--success)' : 
                                                    ach.type === 'motivational' ? 'var(--primary)' : 'var(--info)'
                                                }; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem; text-transform: uppercase;">${
                                                    ach.type === 'streak' ? 'Серия' : 
                                                    ach.type === 'chat' ? 'Чат' : 
                                                    ach.type === 'motivational' ? 'Мотив.' : 'Ачивка'
                                                }</span>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : `
                                <div style="text-align: center; padding: 2rem; color: var(--text-secondary); background: var(--bg-secondary); border-radius: 8px;">
                                    <div style="font-size: 3rem; margin-bottom: 0.5rem; opacity: 0.3;">🏅</div>
                                    <div>Пока нет достижений</div>
                                    <div style="font-size: 0.875rem; margin-top: 0.25rem;">Ответь на вопросы, чтобы получить ачивки!</div>
                                </div>
                            `}
                        </div>
                        
                        <!-- Статистика -->
                        <div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                            <h4 style="margin: 0 0 0.75rem; font-size: 0.9rem;">📊 Статистика</h4>
                            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;">
                                <div>
                                    <div style="font-size: 0.7rem; color: var(--text-secondary);">Отвечено опросов</div>
                                    <div style="font-weight: 600;">${user.answered_polls_count || 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.7rem; color: var(--text-secondary);">Средний балл</div>
                                    <div style="font-weight: 600;">${user.total_answered > 0 ? (user.total_score / user.total_answered).toFixed(2) : 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.7rem; color: var(--text-secondary);">Серия (макс.)</div>
                                    <div style="font-weight: 600;">🔥 ${user.max_streak || 0}</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Активность по чатам -->
                        <h4 style="margin-bottom: 0.75rem;">💬 Активность по чатам (${chats.length})</h4>
                        <div style="max-height: 300px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px;">
                            <table class="data-table" style="margin: 0;">
                                <thead style="position: sticky; top: 0; background: var(--bg-secondary);">
                                    <tr>
                                        <th>Чат</th>
                                        <th style="text-align: right;">Баллы</th>
                                        <th style="text-align: right;">Ответов</th>
                                        <th style="text-align: right;">Серия</th>
                                        <th style="text-align: right;">Макс.</th>
                                        <th>Последний ответ</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${chats.map(chat => `
                                        <tr>
                                            <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(chat.chat_title)}">${escapeHtml(chat.chat_title)}</td>
                                            <td style="text-align: right; font-weight: 600; color: var(--success);">${chat.score}</td>
                                            <td style="text-align: right;">${chat.answered_count}</td>
                                            <td style="text-align: right; color: var(--info);">${chat.consecutive_correct}</td>
                                            <td style="text-align: right; color: var(--warning);">🔥 ${chat.max_consecutive_correct}</td>
                                            <td style="font-size: 0.8rem; color: var(--text-secondary);">${formatDate(chat.last_answer)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <div class="modal-footer" style="justify-content: space-between;">
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn btn-warning btn-sm" onclick="resetUserStats('${userId}')" title="Сбросить статистику">
                                🔄 Сбросить
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="banUser('${userId}', '${escapeHtml(user.name || '')}')" title="Заблокировать">
                                🚫 Бан
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="deleteUser('${userId}', '${escapeHtml(user.name || '')}')" title="Удалить пользователя">
                                🗑️ Удалить
                            </button>
                        </div>
                        <button class="btn btn-secondary" onclick="closeModal('userStatsModal')">Закрыть</button>
                    </div>
                </div>
            </div>
        `;
        
        // Удаляем старые модалки если есть
        const oldModal = document.getElementById('userStatsModal');
        if (oldModal) oldModal.remove();
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
    }
}

// ========== User Management Functions ==========
async function resetUserStats(userId) {
    if (!confirm(`Сбросить всю статистику пользователя ${userId}?\n\nЭто действие нельзя отменить!`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/users/${encodeURIComponent(userId)}/reset-stats`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`✅ ${result.message}`, 'success');
            closeModal('userStatsModal');
            // Обновляем списки
            if (document.getElementById('users')?.classList.contains('active')) {
                loadUsers();
            }
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function banUser(userId, userName) {
    const reason = prompt(`Причина бана пользователя ${userName || userId}:`, 'Нарушение правил');
    if (reason === null) return; // Отмена
    
    try {
        const response = await fetch(`/api/users/${encodeURIComponent(userId)}/ban?reason=${encodeURIComponent(reason)}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`🚫 ${result.message}`, 'success');
            closeModal('userStatsModal');
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function deleteUser(userId, userName) {
    if (!confirm(`УДАЛИТЬ пользователя ${userName || userId} из ВСЕХ чатов?\n\n⚠️ Это действие нельзя отменить!\n\nВся статистика будет потеряна.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/users/${encodeURIComponent(userId)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`🗑️ ${result.message}`, 'success');
            closeModal('userStatsModal');
            // Обновляем списки
            if (document.getElementById('users')?.classList.contains('active')) {
                loadUsers();
            }
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function unbanUser(userId) {
    try {
        const response = await fetch(`/api/users/${encodeURIComponent(userId)}/unban`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok && result.success) {
            showToast(`✅ ${result.message}`, 'success');
            loadBlacklist();
        } else {
            showToast(`❌ ${result.message || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

// ========== Chat Management Functions ==========
async function resetChatStats(chatId) {
    if (!confirm(`Сбросить ВСЮ статистику чата ${chatId}?\n\nНастройки будут сохранены.\n⚠️ Это действие нельзя отменить!`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/reset-stats`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`✅ ${result.message}`, 'success');
            closeModal('chatStatsModal');
            loadChats();
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function deleteChat(chatId) {
    if (!confirm(`УДАЛИТЬ чат ${chatId} и ВСЕ его данные?\n\n⚠️ Это действие нельзя отменить!\n\nБудут удалены:\n- Статистика\n- Настройки\n- Все пользователи чата`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`🗑️ ${result.message}`, 'success');
            closeModal('chatStatsModal');
            loadChats();
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function banChat(chatId) {
    const reason = prompt(`Причина бана чата ${chatId}:`, 'Нарушение правил');
    if (reason === null) return;
    
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/ban?reason=${encodeURIComponent(reason)}`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`🚫 ${result.message}`, 'success');
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function unbanChat(chatId) {
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/unban`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (response.ok && result.success) {
            showToast(`✅ ${result.message}`, 'success');
            loadBlacklist();
        } else {
            showToast(`❌ ${result.message || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function editChatTitle(chatId, currentTitle) {
    const newTitle = prompt('Новое название чата:', currentTitle || '');
    if (newTitle === null || newTitle.trim() === '') return;
    
    try {
        const response = await fetch(`/api/chats/${encodeURIComponent(chatId)}/title?title=${encodeURIComponent(newTitle.trim())}`, {
            method: 'PUT'
        });
        const result = await response.json();
        
        if (response.ok) {
            showToast(`✅ ${result.message}`, 'success');
            loadChats();
        } else {
            showToast(`❌ ${result.detail || 'Ошибка'}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

// ========== Blacklist Functions ==========
async function loadBlacklist() {
    try {
        const response = await fetch('/api/blacklist');
        const data = await response.json();
        
        return data;
    } catch (error) {
        console.error('Error loading blacklist:', error);
        return { users: {}, chats: {} };
    }
}

async function confirmResetAllStats() {
    if (!confirm('⚠️ ВНИМАНИЕ!\n\nВы собираетесь сбросить ВСЮ статистику ВСЕХ чатов!\n\nЭто действие нельзя отменить!\n\nПродолжить?')) {
        return;
    }
    
    const confirmation = prompt('Для подтверждения введите "СБРОСИТЬ ВСЁ":');
    if (confirmation !== 'СБРОСИТЬ ВСЁ') {
        showToast('Сброс отменен', 'info');
        return;
    }
    
    try {
        // Получаем список всех чатов и сбрасываем каждый
        const response = await fetch('/api/chats');
        const chats = await response.json();
        
        let resetCount = 0;
        for (const chat of chats) {
            const resetResponse = await fetch(`/api/chats/${encodeURIComponent(chat.id)}/reset-stats`, {
                method: 'POST'
            });
            if (resetResponse.ok) resetCount++;
        }
        
        showToast(`✅ Статистика сброшена в ${resetCount} чатах`, 'success');
        loadSettings();
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function showBlacklist() {
    try {
        const blacklist = await loadBlacklist();
        const users = Object.entries(blacklist.users || {});
        const chats = Object.entries(blacklist.chats || {});
        
        const formatDate = (dateStr) => {
            if (!dateStr) return '—';
            try {
                return new Date(dateStr).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
            } catch { return '—'; }
        };
        
        const modalHtml = `
            <div class="modal-overlay active" id="blacklistModal" onclick="if(event.target.id === 'blacklistModal') closeModal('blacklistModal')">
                <div class="modal-content" style="max-width: 800px;" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3 class="modal-title">🚫 Черный список</h3>
                        <button class="modal-close-btn" onclick="closeModal('blacklistModal')">×</button>
                    </div>
                    <div class="modal-body">
                        <h4 style="margin-bottom: 0.75rem;">👤 Заблокированные пользователи (${users.length})</h4>
                        ${users.length > 0 ? `
                            <table class="data-table" style="margin-bottom: 1.5rem;">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Имя</th>
                                        <th>Причина</th>
                                        <th>Дата</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${users.map(([userId, data]) => `
                                        <tr>
                                            <td><code>${userId}</code></td>
                                            <td>${escapeHtml(data.name || '—')}</td>
                                            <td>${escapeHtml(data.reason || '—')}</td>
                                            <td>${formatDate(data.banned_at)}</td>
                                            <td><button class="btn btn-sm btn-success" onclick="unbanUser('${userId}')">✓ Разбан</button></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : '<p style="color: var(--text-secondary); margin-bottom: 1.5rem;">Нет заблокированных пользователей</p>'}
                        
                        <h4 style="margin-bottom: 0.75rem;">💬 Заблокированные чаты (${chats.length})</h4>
                        ${chats.length > 0 ? `
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>ID чата</th>
                                        <th>Причина</th>
                                        <th>Дата</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${chats.map(([chatId, data]) => `
                                        <tr>
                                            <td><code>${chatId}</code></td>
                                            <td>${escapeHtml(data.reason || '—')}</td>
                                            <td>${formatDate(data.banned_at)}</td>
                                            <td><button class="btn btn-sm btn-success" onclick="unbanChat('${chatId}')">✓ Разбан</button></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : '<p style="color: var(--text-secondary);">Нет заблокированных чатов</p>'}
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeModal('blacklistModal')">Закрыть</button>
                    </div>
                </div>
            </div>
        `;
        
        const oldModal = document.getElementById('blacklistModal');
        if (oldModal) oldModal.remove();
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
    }
}

async function exportLeaderboard() {
    try {
        window.open('/api/export/statistics', '_blank');
        showToast('Экспорт начат', 'success');
    } catch (error) {
        showToast('Ошибка экспорта', 'error');
    }
}

// ========== Users Section ==========
async function loadUsers() {
    const container = document.getElementById('usersContainer');
    if (!container) return;
    
    container.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка пользователей...</p>';
    
    try {
        const response = await fetch('/api/users');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Ошибка загрузки');
        }
        
        const users = data.users || [];
        
        if (users.length === 0) {
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 3rem;">
                    <div style="font-size: 4rem; margin-bottom: 1rem;">👥</div>
                    <h3 style="margin-bottom: 1rem;">Нет пользователей</h3>
                    <p style="color: var(--text-secondary);">Пользователи появятся после их активности в боте</p>
                </div>
            `;
            return;
        }
        
        // Форматирование даты
        const formatDate = (dateStr) => {
            if (!dateStr) return '—';
            try {
                const d = new Date(dateStr);
                return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });
            } catch { return '—'; }
        };
        
        // Статистика
        const totalScore = users.reduce((sum, u) => sum + u.total_score, 0);
        const totalAnswered = users.reduce((sum, u) => sum + u.total_answered, 0);
        const maxStreak = Math.max(...users.map(u => u.max_streak || 0));
        
        container.innerHTML = `
            <!-- Статистика -->
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--primary);">${users.length}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Пользователей</span>
                </div>
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--success);">${totalScore.toFixed(1)}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Баллов</span>
                </div>
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--info);">${totalAnswered}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Ответов</span>
                </div>
                <div style="background: var(--bg-primary); padding: 1rem 1.5rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <span style="font-size: 1.5rem; font-weight: 700; color: var(--warning);">🔥 ${maxStreak}</span>
                    <span style="color: var(--text-secondary); margin-left: 0.5rem;">Макс. серия</span>
                </div>
            </div>
            
            <!-- Поиск -->
            <div class="card" style="margin-bottom: 1rem; padding: 1rem;">
                <input type="text" id="userSearch" class="form-input" placeholder="🔍 Поиск по имени или ID..." oninput="filterUsers()" style="max-width: 400px;">
            </div>
            
            <!-- Таблица пользователей -->
            <div class="card">
                <div style="max-height: 600px; overflow-y: auto;">
                    <table class="data-table" id="usersTable">
                        <thead style="position: sticky; top: 0; background: var(--bg-primary); z-index: 1;">
                            <tr>
                                <th style="width: 50px;">#</th>
                                <th>Имя</th>
                                <th>ID</th>
                                <th style="text-align: right;">Баллы</th>
                                <th style="text-align: right;">Ответов</th>
                                <th style="text-align: right;">🔥 Серия</th>
                                <th style="text-align: center;">Чатов</th>
                                <th>Первая активность</th>
                                <th>Последняя активность</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${users.map((user, idx) => `
                                <tr style="cursor: pointer;" onclick="viewUserStats('${user.user_id}')" title="Нажмите для подробной информации" data-name="${escapeHtml(user.name || '').toLowerCase()}" data-id="${user.user_id}">
                                    <td>
                                        <span style="display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; background: ${idx < 3 ? ['#fbbf24', '#9ca3af', '#cd7f32'][idx] : 'var(--bg-secondary)'}; color: ${idx < 3 ? 'white' : 'var(--text-primary)'}; font-weight: 600; font-size: 0.8rem;">
                                            ${user.rank || idx + 1}
                                        </span>
                                    </td>
                                    <td style="font-weight: 600;">${escapeHtml(user.name || 'Без имени')}</td>
                                    <td style="font-family: monospace; font-size: 0.8rem; color: var(--text-secondary);">${user.user_id}</td>
                                    <td style="text-align: right; font-weight: 700; color: var(--success);">${user.total_score.toFixed(1)}</td>
                                    <td style="text-align: right;">${user.total_answered}</td>
                                    <td style="text-align: right; color: var(--warning); font-weight: 600;">${user.max_streak || 0}</td>
                                    <td style="text-align: center;">
                                        <span class="badge info">${user.chats_count || 0}</span>
                                    </td>
                                    <td style="font-size: 0.8rem; color: var(--text-secondary);">${formatDate(user.first_activity)}</td>
                                    <td style="font-size: 0.8rem; color: var(--text-secondary);">${formatDate(user.last_activity)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        
        showToast(`Загружено ${users.length} пользователей`, 'success');
    } catch (error) {
        console.error('Error loading users:', error);
        container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem;">Ошибка загрузки: ${escapeHtml(error.message)}</p>`;
        showToast('Ошибка загрузки пользователей', 'error');
    }
}

function filterUsers() {
    const searchValue = document.getElementById('userSearch')?.value.toLowerCase() || '';
    const rows = document.querySelectorAll('#usersTable tbody tr');
    
    rows.forEach(row => {
        const name = row.dataset.name || '';
        const id = row.dataset.id || '';
        
        if (name.includes(searchValue) || id.includes(searchValue)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

async function loadSettings() {
    const container = document.getElementById('settingsContainer');
    if (!container) {
        // Если контейнера нет, используем секцию settings
        const section = document.getElementById('settings');
        if (section) {
            section.innerHTML = `
                <div class="content-header">
                    <h1 class="page-title">Настройки</h1>
                    <div class="header-actions">
                        <button class="btn btn-secondary" onclick="loadSettings()">
                            <span>🔄</span> Обновить
                        </button>
                    </div>
                </div>
                <div id="settingsContainer">
                    <p>Загрузка настроек...</p>
                </div>
            `;
        }
    }
    
    const settingsContainer = document.getElementById('settingsContainer');
    if (!settingsContainer) return;
    
    settingsContainer.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка...</p>';
    
    try {
        const response = await fetch('/api/system/status');
        const status = await response.json();
        
        settingsContainer.innerHTML = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem;">
                <!-- Системный статус -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem;">⚙️ Системный статус</h3>
                    
                    <div class="form-group">
                        <label class="form-label">Режим работы бота</label>
                        <div style="display: flex; align-items: center; gap: 1rem;">
                            <span class="badge ${status.bot_mode === 'main' ? 'success' : 'warning'}" style="font-size: 1rem; padding: 0.5rem 1rem;">
                                ${status.bot_mode === 'main' ? '✅ Основной режим' : '🔧 Обслуживание'}
                            </span>
                            <button class="btn ${status.bot_mode === 'main' ? 'btn-warning' : 'btn-success'}" onclick="toggleBotMode('${status.bot_mode === 'main' ? 'maintenance' : 'main'}')">
                                ${status.bot_mode === 'main' ? '🔧 Включить обслуживание' : '▶️ Включить бота'}
                            </button>
                        </div>
                        ${status.maintenance_reason ? `<p class="form-hint">Причина: ${escapeHtml(status.maintenance_reason)}</p>` : ''}
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Статус бота</label>
                        <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
                            <span class="badge ${status.bot_enabled ? 'success' : 'danger'}" style="font-size: 1rem; padding: 0.5rem 1rem;">
                                ${status.bot_enabled ? '✅ Включен' : '❌ Выключен'}
                            </span>
                            <button class="btn ${status.bot_enabled ? 'btn-danger' : 'btn-success'}" onclick="toggleBotStatus(${!status.bot_enabled})">
                                ${status.bot_enabled ? '⏹️ Выключить' : '▶️ Включить'}
                            </button>
                            <button class="btn btn-warning" onclick="restartBot()" ${!status.bot_enabled ? 'disabled' : ''}>
                                🔄 Перезапустить
                            </button>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Информация</label>
                        <div style="background: var(--bg-secondary); padding: 1rem; border-radius: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                                <span>Активные викторины:</span>
                                <strong>${status.active_quizzes_count || 0}</strong>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span>Подписок на ежедневные:</span>
                                <strong>${status.daily_subscriptions || 0}</strong>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Внешний вид -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem;">🎨 Внешний вид</h3>
                    
                    <div class="form-group">
                        <label class="form-label">Тема интерфейса</label>
                        <div style="display: flex; gap: 1rem;">
                            <button class="btn ${!document.body.classList.contains('dark-mode') ? 'btn-primary' : 'btn-secondary'}" onclick="setTheme('light')">
                                ☀️ Светлая
                            </button>
                            <button class="btn ${document.body.classList.contains('dark-mode') ? 'btn-primary' : 'btn-secondary'}" onclick="setTheme('dark')">
                                🌙 Тёмная
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-top: 1.5rem;">
                <!-- Экспорт и импорт -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem;">📦 Экспорт и импорт</h3>
                    <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                        <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/questions?format=json', '_blank')">
                            📥 Вопросы (JSON)
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/questions?format=csv', '_blank')">
                            📥 Вопросы (CSV)
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/statistics', '_blank')">
                            📊 Статистика
                        </button>
                    </div>
                </div>
                
                <!-- Управление -->
                <div class="card">
                    <h3 style="margin-bottom: 1rem;">🛡️ Управление</h3>
                    <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                        <button class="btn btn-warning btn-sm" onclick="showBlacklist()">
                            🚫 Черный список
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="confirmResetAllStats()">
                            🔄 Сбросить всё
                        </button>
                    </div>
                    <p class="form-hint" style="margin-top: 0.75rem;">
                        Управление заблокированными пользователями и чатами
                    </p>
                </div>
            </div>
            
            <!-- Логи -->
            <div class="card" style="margin-top: 1.5rem;">
                <h3 style="margin-bottom: 1rem;">📋 Просмотр логов</h3>
                <div class="form-group">
                    <label class="form-label">Уровни логирования (можно выбрать несколько)</label>
                    <div style="display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem;">
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" class="log-level-checkbox" value="DEBUG" checked>
                            <span>DEBUG</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" class="log-level-checkbox" value="INFO" checked>
                            <span>INFO</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" class="log-level-checkbox" value="WARNING" checked>
                            <span>WARNING</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" class="log-level-checkbox" value="ERROR" checked>
                            <span>ERROR</span>
                        </label>
                        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                            <input type="checkbox" class="log-level-checkbox" value="CRITICAL" checked>
                            <span>CRITICAL</span>
                        </label>
                    </div>
                    <p class="form-hint" style="margin-top: 0.5rem;">
                        Выберите один или несколько уровней. Если ничего не выбрано, будут показаны все уровни.
                    </p>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div class="form-group">
                        <label class="form-label">С (начало периода)</label>
                        <input type="date" id="logSince" class="form-input">
                        <input type="time" id="logSinceTime" class="form-input" style="margin-top: 0.5rem;">
                    </div>
                    <div class="form-group">
                        <label class="form-label">По (конец периода)</label>
                        <input type="date" id="logUntil" class="form-input">
                        <input type="time" id="logUntilTime" class="form-input" style="margin-top: 0.5rem;">
                    </div>
                </div>
                <div style="display: flex; gap: 0.75rem; margin-bottom: 1rem;">
                    <button class="btn btn-primary" onclick="loadLogs()">
                        🔍 Загрузить логи
                    </button>
                    <button class="btn btn-secondary" onclick="clearLogsView()">
                        🗑️ Очистить
                    </button>
                </div>
                <div id="logsContainer" style="max-height: 600px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; background: var(--bg-secondary);">
                    <p style="text-align: center; color: var(--text-secondary);">Нажмите "Загрузить логи" для просмотра</p>
                </div>
            </div>
            
            <!-- Отправка сообщений админа -->
            <div class="card" style="margin-top: 1.5rem;">
                <h3 style="margin-bottom: 1rem;">📤 Отправка сообщений</h3>
                <div class="form-group">
                    <label class="form-label">Текст сообщения</label>
                    <textarea id="adminMessageText" class="form-input" rows="5" placeholder="Введите текст сообщения, которое бот отправит в чаты..."></textarea>
                    <p class="form-hint">Поддерживается Markdown V2 форматирование (жирный, курсив, ссылки)</p>
                </div>
                <div class="form-group">
                    <label class="form-label">
                        <input type="checkbox" id="sendToAllChats" checked onchange="toggleChatSelection()">
                        Отправить во все чаты
                    </label>
                </div>
                <div id="chatSelectionContainer" class="form-group" style="display: none;">
                    <label class="form-label">Выбрать чаты (можно несколько)</label>
                    <div id="chatsCheckboxList" style="max-height: 300px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px; padding: 0.5rem; background: var(--bg-secondary);">
                        <p style="text-align: center; color: var(--text-secondary);">Загрузка чатов...</p>
                    </div>
                </div>
                <div style="display: flex; gap: 0.75rem; margin-top: 1rem;">
                    <button class="btn btn-primary" onclick="sendAdminMessage()">
                        📤 Отправить сообщение
                    </button>
                </div>
                <div id="adminMessageResult" style="margin-top: 1rem;"></div>
            </div>
        `;
        
        showToast('Настройки загружены', 'success');
    } catch (error) {
        settingsContainer.innerHTML = `<p style="color: var(--danger);">Ошибка загрузки настроек: ${error.message}</p>`;
        showToast('Ошибка загрузки настроек', 'error');
    }
}

async function toggleBotMode(mode) {
    const reason = mode === 'maintenance' ? prompt('Причина перехода в режим обслуживания:', 'Техническое обслуживание') : null;
    if (mode === 'maintenance' && reason === null) return; // Отменено
    
    try {
        showToast('Переключение режима...', 'info');
        
        const response = await fetch(`/api/system/mode?mode=${mode}${reason ? '&reason=' + encodeURIComponent(reason) : ''}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(mode === 'main' ? '✅ Бот переключен в основной режим' : '🔧 Режим обслуживания активирован', 'success');
            
            // Ждем немного, чтобы файлы обновились
            await new Promise(resolve => setTimeout(resolve, 500));
            
            // Обновляем настройки и Dashboard
            await loadSettings();
            await loadDashboard();
        } else {
            showToast(`❌ Ошибка: ${result.detail}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Ошибка: ${error.message}`, 'error');
        console.error('Ошибка переключения режима:', error);
    }
}

async function toggleBotStatus(enabled) {
    try {
        const response = await fetch(`/api/system/bot-status?enabled=${enabled}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showToast(enabled ? 'Бот включен' : 'Бот выключен', 'success');
            // Обновляем настройки и Dashboard
            loadSettings();
            loadDashboard();
        } else {
            showToast(`Ошибка: ${result.detail}`, 'error');
        }
    } catch (error) {
        showToast(`Ошибка: ${error.message}`, 'error');
    }
}

async function restartBot() {
    if (!confirm('Перезапустить бота? Это прервет активные викторины.')) {
        return;
    }
    
    try {
        showToast('Перезапуск бота...', 'info');
        
        const response = await fetch('/api/system/restart-bot', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        // Проверяем тип контента перед парсингом JSON
        const contentType = response.headers.get('content-type');
        let result;
        
        if (contentType && contentType.includes('application/json')) {
            try {
                result = await response.json();
            } catch (jsonError) {
                // Если не удалось распарсить JSON, читаем текст
                const text = await response.text();
                throw new Error(`Ошибка парсинга JSON: ${text.substring(0, 200)}`);
            }
        } else {
            // Если ответ не JSON, читаем как текст
            const text = await response.text();
            throw new Error(`Сервер вернул не JSON: ${text.substring(0, 200)}`);
        }
        
        if (response.ok) {
            showToast(result.message || 'Бот перезапущен успешно', 'success');
            // Обновляем настройки и Dashboard через 2 секунды
            setTimeout(() => {
                loadSettings();
                loadDashboard();
            }, 2000);
        } else {
            const errorMsg = result.detail || result.message || 'Неизвестная ошибка';
            showToast(`Ошибка: ${errorMsg}`, 'error');
        }
    } catch (error) {
        console.error('Ошибка при перезапуске бота:', error);
        const errorMsg = error.message || 'Не удалось перезапустить бота';
        showToast(`Ошибка: ${errorMsg}`, 'error');
    }
}

function setTheme(theme) {
    if (theme === 'dark') {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    localStorage.setItem('darkMode', theme === 'dark');
    
    // Перезагружаем графики с новой темой если на dashboard
    if (document.querySelector('#dashboard.active')) {
        loadCharts();
    }
    
    // Обновляем кнопки в настройках
    loadSettings();
}

// ========== Utilities ==========
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// ================== ЛОГИ ==================

async function loadLogs() {
    const container = document.getElementById('logsContainer');
    if (!container) return;
    
    try {
        container.innerHTML = '<p style="text-align: center; padding: 2rem;"><span class="loading"></span> Загрузка логов...</p>';
        
        // Собираем выбранные уровни логирования
        const levelCheckboxes = document.querySelectorAll('.log-level-checkbox:checked');
        const selectedLevels = Array.from(levelCheckboxes).map(cb => cb.value);
        const level = selectedLevels.length > 0 ? selectedLevels.join(',') : '';
        
        const sinceDate = document.getElementById('logSince')?.value || '';
        const sinceTime = document.getElementById('logSinceTime')?.value || '';
        const untilDate = document.getElementById('logUntil')?.value || '';
        const untilTime = document.getElementById('logUntilTime')?.value || '';
        
        let since = null;
        let until = null;
        
        if (sinceDate) {
            since = sinceTime ? `${sinceDate}T${sinceTime}` : sinceDate;
        }
        if (untilDate) {
            until = untilTime ? `${untilDate}T${untilTime}` : untilDate;
        }
        
        const params = new URLSearchParams();
        if (level) params.append('level', level);
        if (since) params.append('since', since);
        if (until) params.append('until', until);
        params.append('limit', '500');
        
        const response = await fetch(`/api/logs?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        const logs = data.logs || [];
        
        if (logs.length === 0) {
            container.innerHTML = '<p style="text-align: center; padding: 2rem; color: var(--text-secondary);">Логи не найдены для указанных фильтров</p>';
            return;
        }
        
        const levelColors = {
            'DEBUG': 'var(--text-secondary)',
            'INFO': 'var(--info)',
            'WARNING': 'var(--warning)',
            'ERROR': 'var(--danger)',
            'CRITICAL': 'var(--danger)'
        };
        
        container.innerHTML = `
            <div style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.875rem;">
                Найдено записей: <strong>${logs.length}</strong>
            </div>
            <div style="font-family: 'Courier New', monospace; font-size: 0.875rem; line-height: 1.6;">
                ${logs.map(log => {
                    const levelColor = levelColors[log.level] || 'var(--text-primary)';
                    const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleString('ru-RU') : '—';
                    const logger = log.logger || '—';
                    return `
                        <div style="border-bottom: 1px solid var(--border-color); padding: 0.5rem 0;">
                            <div style="display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.25rem;">
                                <span style="color: ${levelColor}; font-weight: 600;">[${log.level}]</span>
                                <span style="color: var(--text-secondary);">${timestamp}</span>
                                <span style="color: var(--text-secondary);">${logger}</span>
                            </div>
                            <div style="color: var(--text-primary); word-break: break-word;">${escapeHtml(log.message)}</div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        
        showToast(`Загружено ${logs.length} записей логов`, 'success');
    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger); text-align: center; padding: 2rem;">Ошибка загрузки логов: ${escapeHtml(error.message)}</p>`;
        showToast(`Ошибка загрузки логов: ${error.message}`, 'error');
    }
}

function clearLogsView() {
    // Сбрасываем все чекбоксы уровней логирования
    document.querySelectorAll('.log-level-checkbox').forEach(cb => {
        cb.checked = true; // По умолчанию все выбраны
    });
    document.getElementById('logSince').value = '';
    document.getElementById('logSinceTime').value = '';
    document.getElementById('logUntil').value = '';
    document.getElementById('logUntilTime').value = '';
    document.getElementById('logsContainer').innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Нажмите "Загрузить логи" для просмотра</p>';
}

// ================== ОТПРАВКА СООБЩЕНИЙ АДМИНА ==================

async function loadChatsForMessage() {
    const container = document.getElementById('chatsCheckboxList');
    if (!container) return;
    
    try {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Загрузка чатов...</p>';
        
        const response = await fetch('/api/chats');
        if (!response.ok) {
            throw new Error(`Ошибка ${response.status}`);
        }
        
        const chats = await response.json();
        
        if (chats.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">Чаты не найдены</p>';
            return;
        }
        
        // Сортируем чаты по названию
        const sortedChats = [...chats].sort((a, b) => {
            const titleA = (a.title || `Чат ${a.id}`).toLowerCase();
            const titleB = (b.title || `Чат ${b.id}`).toLowerCase();
            return titleA.localeCompare(titleB);
        });
        
        container.innerHTML = `
            ${sortedChats.map(chat => `
                <label style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; cursor: pointer; border-radius: 6px; transition: background 0.2s; margin-bottom: 0.25rem;" 
                       onmouseover="this.style.background='var(--bg-hover)'" 
                       onmouseout="this.style.background='transparent'"
                       title="ID: ${chat.id}">
                    <input type="checkbox" value="${chat.id}" class="chat-checkbox" style="cursor: pointer; width: 18px; height: 18px; flex-shrink: 0;">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${escapeHtml(chat.title || `Чат ${chat.id}`)}
                        </div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary);">
                            ID: ${chat.id}
                            ${chat.daily_quiz_enabled ? ' • 📅 Ежедневная викторина' : ''}
                        </div>
                    </div>
                </label>
            `).join('')}
        `;
    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger); text-align: center;">Ошибка загрузки чатов: ${escapeHtml(error.message)}</p>`;
    }
}

function toggleChatSelection() {
    const sendToAll = document.getElementById('sendToAllChats').checked;
    const container = document.getElementById('chatSelectionContainer');
    
    if (sendToAll) {
        container.style.display = 'none';
    } else {
        container.style.display = 'block';
        // Загружаем чаты только если список еще не загружен
        const checkboxList = document.getElementById('chatsCheckboxList');
        if (!checkboxList.querySelector('.chat-checkbox')) {
            loadChatsForMessage();
        }
    }
}

async function sendAdminMessage() {
    const messageText = document.getElementById('adminMessageText')?.value?.trim();
    if (!messageText) {
        showToast('Введите текст сообщения', 'warning');
        return;
    }
    
    const sendToAll = document.getElementById('sendToAllChats').checked;
    const resultContainer = document.getElementById('adminMessageResult');
    
    let chatIds = null;
    if (!sendToAll) {
        const checkboxes = document.querySelectorAll('.chat-checkbox:checked');
        if (checkboxes.length === 0) {
            showToast('Выберите хотя бы один чат', 'warning');
            return;
        }
        chatIds = Array.from(checkboxes).map(cb => cb.value);
    }
    
    try {
        resultContainer.innerHTML = '<p style="text-align: center; color: var(--info);"><span class="loading"></span> Отправка сообщений...</p>';
        showToast('Отправка сообщений...', 'info');
        
        const response = await fetch('/api/admin/send-message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: messageText,
                send_to_all: sendToAll,
                chat_ids: chatIds
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `Ошибка ${response.status}`);
        }
        
        const result = await response.json();
        const successCount = result.results?.success?.length || 0;
        const failedCount = result.results?.failed?.length || 0;
        const total = result.results?.total || 0;
        
        let resultHtml = `
            <div style="padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-weight: 600; margin-bottom: 0.5rem; color: ${successCount > 0 ? 'var(--success)' : 'var(--danger)'};">
                    ${result.message || `Отправлено: ${successCount}/${total}`}
                </div>
        `;
        
        if (failedCount > 0) {
            resultHtml += `
                <div style="margin-top: 0.75rem;">
                    <div style="font-weight: 600; color: var(--warning); margin-bottom: 0.5rem;">Ошибки (${failedCount}):</div>
                    <div style="max-height: 150px; overflow-y: auto; font-size: 0.875rem;">
                        ${result.results.failed.map(f => `
                            <div style="margin-bottom: 0.25rem; color: var(--danger);">
                                Чат ${f.chat_id}: ${escapeHtml(f.error)}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
        
        resultHtml += '</div>';
        resultContainer.innerHTML = resultHtml;
        
        if (successCount > 0) {
            showToast(`Сообщение отправлено в ${successCount} чат(ов)`, 'success');
            // Очищаем поле сообщения после успешной отправки
            document.getElementById('adminMessageText').value = '';
        } else {
            showToast('Не удалось отправить сообщение ни в один чат', 'error');
        }
    } catch (error) {
        resultContainer.innerHTML = `
            <div style="padding: 1rem; background: var(--bg-secondary); border-radius: 8px; color: var(--danger);">
                Ошибка: ${escapeHtml(error.message)}
            </div>
        `;
        showToast(`Ошибка отправки: ${error.message}`, 'error');
    }
}
