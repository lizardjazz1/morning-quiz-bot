// Global variables
let charts = {};
let allQuestions = [];
let allCategories = [];
let currentCategory = null;
let allChats = [];

// ========== Initialization ==========
document.addEventListener('DOMContentLoaded', () => {
    initDarkMode();
    initNavigation();
    loadDashboard();
});

// ========== Toast Notifications ==========
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span style="font-size: 1.5rem;">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ========== Dark Mode ==========
function initDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    const isDark = localStorage.getItem('darkMode') === 'true';
    
    if (isDark) {
        document.body.classList.add('dark-mode');
    }
    
    darkModeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
    });
}

// ========== Navigation ==========
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const sectionId = item.getAttribute('data-section');
            
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            sections.forEach(section => section.classList.remove('active'));
            const targetSection = document.getElementById(sectionId);
            if (targetSection) {
                targetSection.classList.add('active');
                
                if (sectionId === 'dashboard') {
                    loadDashboard();
                } else if (sectionId === 'questions') {
                    loadQuestions();
                } else if (sectionId === 'chats') {
                    loadChats();
                } else if (sectionId === 'analytics') {
                    loadAnalytics();
                } else if (sectionId === 'photo-quiz') {
                    loadPhotoQuiz();
                } else if (sectionId === 'settings') {
                    loadSettings();
                }
            }
        });
    });
}

// ========== Dashboard ==========
async function loadDashboard() {
    try {
        const response = await fetch('/api/analytics/dashboard');
        const data = await response.json();
        
        document.getElementById('totalUsers').textContent = data.total_users || 0;
        document.getElementById('totalQuizzes').textContent = data.total_quizzes || 0;
        document.getElementById('totalQuestionsDB').textContent = data.total_questions_db || 0;
        document.getElementById('totalCategories').textContent = data.total_categories || 0;
        document.getElementById('totalPhotoQuiz').textContent = data.total_photo_quiz || 0;
        document.getElementById('totalChats').textContent = data.total_chats || 0;
        
        await loadCharts();
        showToast('Панель управления загружена', 'success');
    } catch (error) {
        showToast('Ошибка загрузки панели', 'error');
    }
}

async function loadCharts() {
    // Destroy existing charts
    Object.values(charts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            chart.destroy();
        }
    });
    charts = {};
    
    try {
        const [activity, categories, users, scores] = await Promise.all([
            fetch('/api/analytics/charts/activity').then(r => r.json()),
            fetch('/api/analytics/charts/categories').then(r => r.json()),
            fetch('/api/analytics/charts/users').then(r => r.json()),
            fetch('/api/analytics/charts/score-distribution').then(r => r.json())
        ]);
        
        const isDark = document.body.classList.contains('dark-mode');
        const textColor = isDark ? '#e5e7eb' : '#374151';
        const gridColor = isDark ? '#374151' : '#e5e7eb';
        
        // Activity Chart
        const activityCtx = document.getElementById('activityChart');
        if (activityCtx) {
            charts.activity = new Chart(activityCtx, {
                type: 'line',
                data: {
                    labels: activity.labels,
                    datasets: [{
                        label: 'Активность',
                        data: activity.data,
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: textColor } }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        },
                        x: {
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        }
                    }
                }
            });
        }
        
        // Categories Chart
        const categoriesCtx = document.getElementById('categoriesChart');
        if (categoriesCtx) {
            charts.categories = new Chart(categoriesCtx, {
                type: 'bar',
                data: {
                    labels: categories.labels,
                    datasets: [{
                        label: 'Вопросов',
                        data: categories.data,
                        backgroundColor: '#10b981'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: textColor } }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        },
                        x: {
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        }
                    }
                }
            });
        }
        
        // Users Chart
        const usersCtx = document.getElementById('usersChart');
        if (usersCtx) {
            charts.users = new Chart(usersCtx, {
                type: 'doughnut',
                data: {
                    labels: users.labels,
                    datasets: [{
                        data: users.data,
                        backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: textColor } }
                    }
                }
            });
        }
        
        // Score Distribution Chart
        const scoresCtx = document.getElementById('scoreDistChart');
        if (scoresCtx) {
            charts.scores = new Chart(scoresCtx, {
                type: 'bar',
                data: {
                    labels: scores.labels,
                    datasets: [{
                        label: 'Количество',
                        data: scores.data,
                        backgroundColor: '#8b5cf6'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { labels: { color: textColor } }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        },
                        x: {
                            ticks: { color: textColor },
                            grid: { color: gridColor }
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('Error loading charts:', error);
    }
}

// ========== Questions & Categories ==========
async function loadQuestions() {
    try {
        const [questionsRes, categoriesRes] = await Promise.all([
            fetch('/api/questions'),
            fetch('/api/categories')
        ]);
        
        allQuestions = await questionsRes.json();
        allCategories = await categoriesRes.json();
        
        renderCategoriesList();
        renderQuestions();
        showToast('Вопросы загружены', 'success');
    } catch (error) {
        showToast('Ошибка загрузки вопросов', 'error');
        console.error(error);
    }
}

function renderCategoriesList() {
    const container = document.getElementById('categoriesList');
    
    if (!allCategories || allCategories.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.875rem;">Нет категорий</p>';
        return;
    }
    
    container.innerHTML = allCategories.map(cat => `
        <div class="category-item ${currentCategory === cat.id ? 'active' : ''}" onclick="filterByCategory('${cat.id}')">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>${cat.name}</span>
                <span class="badge">${getQuestionsByCategory(cat.id).length}</span>
            </div>
        </div>
    `).join('');
}

function getQuestionsByCategory(categoryId) {
    return allQuestions.filter(q => q.category === categoryId);
}

function filterByCategory(categoryId) {
    currentCategory = categoryId;
    renderCategoriesList();
    renderQuestions();
    
    const category = allCategories.find(c => c.id === categoryId);
    const info = document.getElementById('currentCategoryInfo');
    const nameEl = document.getElementById('currentCategoryName');
    const countEl = document.getElementById('currentCategoryCount');
    
    if (category) {
        info.style.display = 'block';
        nameEl.textContent = category.name;
        const questions = getQuestionsByCategory(categoryId);
        countEl.textContent = `(${questions.length} вопросов)`;
    }
}

function showAllQuestions() {
    currentCategory = null;
    renderCategoriesList();
    renderQuestions();
    document.getElementById('currentCategoryInfo').style.display = 'none';
}

function renderQuestions() {
    const container = document.getElementById('questionsContainer');
    let questions = currentCategory 
        ? getQuestionsByCategory(currentCategory)
        : allQuestions;
    
    const search = document.getElementById('questionSearch').value.toLowerCase();
    if (search) {
        questions = questions.filter(q => 
            q.question.toLowerCase().includes(search) ||
            (q.correct_answer && q.correct_answer.toLowerCase().includes(search))
        );
    }
    
    if (questions.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">Нет вопросов</p>';
        return;
    }
    
    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 50%;">Вопрос</th>
                    <th style="width: 20%;">Категория</th>
                    <th style="width: 15%;">Тип</th>
                    <th style="width: 15%;">Действия</th>
                </tr>
            </thead>
            <tbody>
                ${questions.map(q => {
                    const category = allCategories.find(c => c.id === q.category);
                    return `
                        <tr>
                            <td>${escapeHtml(q.question)}</td>
                            <td>${category ? category.name : q.category}</td>
                            <td><span class="badge">${q.type || 'quiz'}</span></td>
                            <td>
                                <button class="btn btn-sm btn-primary" onclick="editQuestion('${q.category}', '${q.id}')" title="Редактировать">
                                    ✏️
                                </button>
                                <button class="btn btn-sm btn-danger" onclick="deleteQuestion('${q.category}', '${q.id}')" title="Удалить">
                                    🗑️
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
}

function filterQuestions() {
    renderQuestions();
}

// ========== Modal Functions ==========
function openAddQuestionModal() {
    const modal = createModal('Добавить вопрос', `
        <div class="form-group">
            <label class="form-label required">Категория</label>
            <select id="modalCategory" class="form-select">
                ${allCategories.map(c => `<option value="${c.id}">${c.name}</option>`).join('')}
            </select>
        </div>
        <div class="form-group">
            <label class="form-label required">Вопрос</label>
            <textarea id="modalQuestion" class="form-textarea" rows="3" placeholder="Введите вопрос..."></textarea>
        </div>
        <div class="form-group">
            <label class="form-label required">Правильный ответ</label>
            <input type="text" id="modalCorrectAnswer" class="form-input" placeholder="Правильный ответ">
        </div>
        <div class="form-group">
            <label class="form-label">Варианты ответов (опционально)</label>
            <div id="optionsList">
                <div class="option-item">
                    <input type="text" class="form-input" placeholder="Вариант 1">
                </div>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="addOption()" style="margin-top: 0.5rem;">
                ➕ Добавить вариант
            </button>
        </div>
    `, [
        { label: 'Отмена', class: 'btn-secondary', onclick: 'closeModal()' },
        { label: 'Сохранить', class: 'btn-primary', onclick: 'saveNewQuestion()' }
    ]);
    
    showModal(modal);
}

async function saveNewQuestion() {
    const category = document.getElementById('modalCategory').value;
    const question = document.getElementById('modalQuestion').value.trim();
    const correctAnswer = document.getElementById('modalCorrectAnswer').value.trim();
    
    if (!question || !correctAnswer) {
        showToast('Заполните обязательные поля', 'error');
        return;
    }
    
    const options = Array.from(document.querySelectorAll('#optionsList input'))
        .map(input => input.value.trim())
        .filter(val => val);
    
    const newQuestion = {
        question,
        correct_answer: correctAnswer,
        type: 'quiz'
    };
    
    if (options.length > 0) {
        newQuestion.options = options;
    }
    
    try {
        const response = await fetch(`/api/categories/${category}/questions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newQuestion)
        });
        
        if (response.ok) {
            showToast('Вопрос добавлен', 'success');
            closeModal();
            loadQuestions();
        } else {
            showToast('Ошибка при добавлении вопроса', 'error');
        }
    } catch (error) {
        showToast('Ошибка сети', 'error');
        console.error(error);
    }
}

function addOption() {
    const list = document.getElementById('optionsList');
    const div = document.createElement('div');
    div.className = 'option-item';
    div.style.marginTop = '0.5rem';
    div.innerHTML = `
        <div style="display: flex; gap: 0.5rem;">
            <input type="text" class="form-input" placeholder="Вариант ответа">
            <button class="btn btn-danger btn-sm" onclick="this.parentElement.parentElement.remove()">✕</button>
        </div>
    `;
    list.appendChild(div);
}

async function editQuestion(categoryId, questionId) {
    try {
        const response = await fetch(`/api/categories/${categoryId}/questions/${questionId}`);
        const question = await response.json();
        
        const modal = createModal('Редактировать вопрос', `
            <div class="form-group">
                <label class="form-label required">Вопрос</label>
                <textarea id="modalQuestion" class="form-textarea" rows="3">${escapeHtml(question.question)}</textarea>
            </div>
            <div class="form-group">
                <label class="form-label required">Правильный ответ</label>
                <input type="text" id="modalCorrectAnswer" class="form-input" value="${escapeHtml(question.correct_answer || '')}">
            </div>
            <div class="form-group">
                <label class="form-label">Варианты ответов</label>
                <div id="optionsList">
                    ${(question.options || []).map(opt => `
                        <div class="option-item" style="margin-top: 0.5rem;">
                            <div style="display: flex; gap: 0.5rem;">
                                <input type="text" class="form-input" value="${escapeHtml(opt)}">
                                <button class="btn btn-danger btn-sm" onclick="this.parentElement.parentElement.remove()">✕</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <button class="btn btn-secondary btn-sm" onclick="addOption()" style="margin-top: 0.5rem;">
                    ➕ Добавить вариант
                </button>
            </div>
        `, [
            { label: 'Отмена', class: 'btn-secondary', onclick: 'closeModal()' },
            { label: 'Сохранить', class: 'btn-primary', onclick: `saveEditedQuestion('${categoryId}', '${questionId}')` }
        ]);
        
        showModal(modal);
    } catch (error) {
        showToast('Ошибка загрузки вопроса', 'error');
    }
}

async function saveEditedQuestion(categoryId, questionId) {
    const question = document.getElementById('modalQuestion').value.trim();
    const correctAnswer = document.getElementById('modalCorrectAnswer').value.trim();
    
    if (!question || !correctAnswer) {
        showToast('Заполните обязательные поля', 'error');
        return;
    }
    
    const options = Array.from(document.querySelectorAll('#optionsList input'))
        .map(input => input.value.trim())
        .filter(val => val);
    
    const updatedQuestion = {
        question,
        correct_answer: correctAnswer,
        type: 'quiz'
    };
    
    if (options.length > 0) {
        updatedQuestion.options = options;
    }
    
    try {
        const response = await fetch(`/api/categories/${categoryId}/questions/${questionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updatedQuestion)
        });
        
        if (response.ok) {
            showToast('Вопрос обновлен', 'success');
            closeModal();
            loadQuestions();
        } else {
            showToast('Ошибка при обновлении вопроса', 'error');
        }
    } catch (error) {
        showToast('Ошибка сети', 'error');
        console.error(error);
    }
}

async function deleteQuestion(categoryId, questionId) {
    if (!confirm('Вы уверены, что хотите удалить этот вопрос?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/categories/${categoryId}/questions/${questionId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Вопрос удален', 'success');
            loadQuestions();
        } else {
            showToast('Ошибка при удалении вопроса', 'error');
        }
    } catch (error) {
        showToast('Ошибка сети', 'error');
        console.error(error);
    }
}

// ========== Chats & Subscriptions ==========
async function loadChats() {
    try {
        const response = await fetch('/api/chats');
        allChats = await response.json();
        renderChats();
        showToast('Чаты загружены', 'success');
    } catch (error) {
        showToast('Ошибка загрузки чатов', 'error');
        console.error(error);
    }
}

function renderChats() {
    const container = document.getElementById('chatsContainer');
    
    if (allChats.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">Нет чатов</p>';
        return;
    }
    
    container.innerHTML = allChats.map(chat => `
        <div class="card" style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
                <div>
                    <h3 style="margin: 0; font-size: 1.125rem;">${chat.title || `Чат ${chat.id}`}</h3>
                    <p style="color: var(--text-secondary); font-size: 0.875rem; margin: 0.25rem 0 0;">ID: ${chat.id}</p>
                </div>
                <span class="badge ${chat.daily_quiz_enabled ? 'success' : 'secondary'}">
                    ${chat.daily_quiz_enabled ? '✓ Активна' : '✗ Выключена'}
                </span>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem;">
                <div class="stat-card">
                    <div class="stat-value">${chat.users_count || 0}</div>
                    <div class="stat-label">Пользователей</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${chat.total_quizzes || 0}</div>
                    <div class="stat-label">Викторин</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${(chat.daily_quiz_times || []).length}</div>
                    <div class="stat-label">Расписаний</div>
                </div>
            </div>
            
            ${chat.daily_quiz_enabled ? `
                <div style="margin-bottom: 1rem;">
                    <h4 style="font-size: 0.875rem; margin-bottom: 0.5rem; color: var(--text-secondary);">Время запуска:</h4>
                    <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                        ${(chat.daily_quiz_times || []).map(time => `
                            <span class="badge primary">${time}</span>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div style="display: flex; gap: 0.75rem;">
                <button class="btn btn-primary btn-sm" onclick="editChatSubscription(${chat.id})">
                    ⚙️ Настроить расписание
                </button>
                <button class="btn ${chat.daily_quiz_enabled ? 'btn-secondary' : 'btn-success'} btn-sm" 
                        onclick="toggleChatSubscription(${chat.id}, ${!chat.daily_quiz_enabled})">
                    ${chat.daily_quiz_enabled ? '⏸️ Отключить' : '▶️ Включить'}
                </button>
            </div>
        </div>
    `).join('');
}

async function editChatSubscription(chatId) {
    const chat = allChats.find(c => c.id === chatId);
    if (!chat) return;
    
    const times = chat.daily_quiz_times || [];
    
    const modal = createModal(`Расписание для "${chat.title || chatId}"`, `
        <div class="form-group">
            <label class="form-label">Время запуска викторин</label>
            <div id="timesList">
                ${times.map(time => `
                    <div class="time-item" style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <input type="time" class="form-input" value="${time}">
                        <button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()">✕</button>
                    </div>
                `).join('')}
            </div>
            <button class="btn btn-secondary btn-sm" onclick="addTimeSlot()" style="margin-top: 0.5rem;">
                ➕ Добавить время
            </button>
        </div>
        <div class="form-hint">Укажите время в формате 24 часа (например, 09:00, 14:30)</div>
    `, [
        { label: 'Отмена', class: 'btn-secondary', onclick: 'closeModal()' },
        { label: 'Сохранить', class: 'btn-primary', onclick: `saveChatSchedule(${chatId})` }
    ]);
    
    showModal(modal);
}

function addTimeSlot() {
    const list = document.getElementById('timesList');
    const div = document.createElement('div');
    div.className = 'time-item';
    div.style.display = 'flex';
    div.style.gap = '0.5rem';
    div.style.marginBottom = '0.5rem';
    div.innerHTML = `
        <input type="time" class="form-input">
        <button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()">✕</button>
    `;
    list.appendChild(div);
}

async function saveChatSchedule(chatId) {
    const times = Array.from(document.querySelectorAll('#timesList input'))
        .map(input => input.value)
        .filter(val => val);
    
    if (times.length === 0) {
        showToast('Добавьте хотя бы одно время', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/chats/${chatId}/subscription`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ times })
        });
        
        if (response.ok) {
            showToast('Расписание обновлено', 'success');
            closeModal();
            loadChats();
        } else {
            showToast('Ошибка при обновлении расписания', 'error');
        }
    } catch (error) {
        showToast('Ошибка сети', 'error');
        console.error(error);
    }
}

async function toggleChatSubscription(chatId, enabled) {
    try {
        const response = await fetch(`/api/chats/${chatId}/subscription/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        
        if (response.ok) {
            showToast(enabled ? 'Подписка включена' : 'Подписка отключена', 'success');
            loadChats();
        } else {
            showToast('Ошибка при изменении подписки', 'error');
        }
    } catch (error) {
        showToast('Ошибка сети', 'error');
        console.error(error);
    }
}

// ========== Modal Utilities ==========
function createModal(title, content, buttons) {
    return `
        <div class="modal-overlay active" id="modalOverlay" onclick="closeModalOnOverlayClick(event)">
            <div class="modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">${title}</h3>
                    <button class="modal-close" onclick="closeModal()">✕</button>
                </div>
                <div class="modal-body">
                    ${content}
                </div>
                <div class="modal-footer">
                    ${buttons.map(btn => `
                        <button class="btn ${btn.class}" onclick="${btn.onclick}">${btn.label}</button>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

function showModal(html) {
    const container = document.getElementById('modalContainer');
    container.innerHTML = html;
}

function closeModal() {
    const container = document.getElementById('modalContainer');
    container.innerHTML = '';
}

function closeModalOnOverlayClick(event) {
    if (event.target.id === 'modalOverlay') {
        closeModal();
    }
}

// ========== Utilities ==========
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========== Analytics, Photo Quiz, Settings ==========
async function loadAnalytics() {
    showToast('Аналитика загружается...', 'info');
}

async function loadPhotoQuiz() {
    showToast('Фотовикторина загружается...', 'info');
}

async function loadSettings() {
    showToast('Настройки загружаются...', 'info');
}
