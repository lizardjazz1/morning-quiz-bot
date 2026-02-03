// Chats and Subscriptions Management Module
// Variables are defined in app.js

// Load chats
async function loadChats() {
    try {
        const [chatsResponse, statsResponse] = await Promise.all([
            fetch('/api/chats'),
            fetch('/api/statistics')
        ]);
        
        const chatsData = await chatsResponse.json();
        const statsData = await statsResponse.json();
        
        allChats = Array.isArray(chatsData) ? chatsData : (chatsData.chats || []);
        displayChats(allChats);
        
        showToast(`Загружено ${allChats.length} чатов`, 'success');
    } catch (error) {
        console.error('Error loading chats:', error);
        showToast('Ошибка загрузки чатов', 'error');
    }
}

// Display chats
function displayChats(chats) {
    const container = document.getElementById('chatsContainer');
    
    if (chats.length === 0) {
        container.innerHTML = '<p>Чаты не найдены.</p>';
        return;
    }
    
    const html = `
        <div class="stats-grid">
            ${chats.map(chat => `
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-title">${chat.chat_name || `Чат ${chat.chat_id}`}</div>
                            <div class="stat-subtitle">ID: ${chat.chat_id}</div>
                        </div>
                        <div class="stat-icon">💬</div>
                    </div>
                    <div class="stat-body" style="margin-top: 1rem;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="color: var(--text-secondary); font-size: 0.875rem;">Пользователей:</span>
                            <strong>${chat.user_count || 0}</strong>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                            <span style="color: var(--text-secondary); font-size: 0.875rem;">Ежедневная викторина:</span>
                            <span style="font-weight: 600; color: ${chat.daily_quiz_enabled ? 'var(--success)' : 'var(--danger)'};">
                                ${chat.daily_quiz_enabled ? '✓ Включена' : '✗ Выключена'}
                            </span>
                        </div>
                        ${chat.daily_quiz_times && chat.daily_quiz_times.length > 0 ? `
                        <div style="margin-top: 0.75rem;">
                            <span style="color: var(--text-secondary); font-size: 0.875rem;">Время запуска:</span>
                            <div style="margin-top: 0.25rem; display: flex; flex-wrap: wrap; gap: 0.25rem;">
                                ${chat.daily_quiz_times.map(time => 
                                    `<span style="background: var(--primary); color: white; padding: 0.125rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${time}</span>`
                                ).join('')}
                            </div>
                        </div>
                        ` : ''}
                    </div>
                    <div class="stat-footer" style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                        <button class="btn btn-secondary" style="flex: 1; font-size: 0.875rem;" onclick="viewChatDetails('${chat.chat_id}')">
                            📊 Подробнее
                        </button>
                        <button class="btn btn-primary" style="flex: 1; font-size: 0.875rem;" onclick="editChatSettings('${chat.chat_id}')">
                            ⚙️ Настроить
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    container.innerHTML = html;
}

// View chat details
async function viewChatDetails(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}/detailed`);
        if (!response.ok) throw new Error('Failed to load chat details');

        const data = await response.json();

        const modalHtml = `
            <div class="modal-overlay active" id="chatDetailsModal" onclick="closeModal('chatDetailsModal')">
                <div class="modal" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3 class="modal-title">Подробная информация о чате</h3>
                        <button class="modal-close" onclick="closeModal('chatDetailsModal')">×</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label class="form-label">Название чата</label>
                            <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">${data.chat_name || 'Без названия'}</div>
                        </div>

                        <div class="form-group">
                            <label class="form-label">ID чата</label>
                            <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px; font-family: monospace;">${chatId}</div>
                        </div>

                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin: 1.5rem 0;">
                            <div class="kpi-card">
                                <div class="kpi-label">Пользователей</div>
                                <div class="kpi-value">${data.user_count || 0}</div>
                            </div>
                            <div class="kpi-card">
                                <div class="kpi-label">Викторин запущено</div>
                                <div class="kpi-value">${data.total_quizzes || 0}</div>
                            </div>
                        </div>

                        <div class="form-group">
                            <label class="form-label">Ежедневная викторина</label>
                            <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">
                                <div style="margin-bottom: 0.5rem;">
                                    <strong>Статус:</strong>
                                    <span style="color: ${data.daily_quiz_enabled ? 'var(--success)' : 'var(--danger)'}; font-weight: 600;">
                                        ${data.daily_quiz_enabled ? '✓ Включена' : '✗ Выключена'}
                                    </span>
                                </div>
                                ${data.daily_quiz_times && data.daily_quiz_times.length > 0 ? `
                                <div>
                                    <strong>Время запуска:</strong><br>
                                    ${data.daily_quiz_times.map(time =>
                                        `<span style="display: inline-block; margin: 0.25rem 0.25rem 0 0; background: var(--primary); color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.875rem;">${time}</span>`
                                    ).join('')}
                                </div>
                                ` : '<div><strong>Время:</strong> Не настроено</div>'}
                            </div>
                        </div>

                        ${data.top_users && data.top_users.length > 0 ? `
                        <div class="form-group">
                            <label class="form-label">Топ пользователей</label>
                            <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">
                                ${data.top_users.slice(0, 5).map((user, idx) => `
                                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; ${idx < data.top_users.length - 1 ? 'border-bottom: 1px solid var(--border-color);' : ''}">
                                        <span>${user.name || 'Пользователь ' + user.user_id}</span>
                                        <strong>${user.total_score || 0} 🏆</strong>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                        ` : ''}
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeModal('chatDetailsModal')">Закрыть</button>
                        <button class="btn btn-primary" onclick="closeModal('chatDetailsModal'); editChatSettings('${chatId}')">Настроить</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        console.error('Error loading chat details:', error);
        showToast('Ошибка загрузки данных чата', 'error');
    }
}

// Edit chat settings
async function editChatSettings(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        if (!response.ok) throw new Error('Failed to load chat settings');
        
        const chat = await response.json();
        
        const modalHtml = `
            <div class="modal-overlay active" id="chatSettingsModal" onclick="closeModal('chatSettingsModal')">
                <div class="modal" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3 class="modal-title">Настройки чата</h3>
                        <button class="modal-close" onclick="closeModal('chatSettingsModal')">×</button>
                    </div>
                    <div class="modal-body">
                        <form id="chatSettingsForm">
                            <div class="form-group">
                                <label class="form-label">Название чата</label>
                                <input type="text" class="form-input" id="chatName" value="${chat.chat_name || ''}" readonly style="background: var(--bg-secondary);">
                                <p class="form-hint">ID: ${chatId}</p>
                            </div>
                            
                            <div class="form-group">
                                <label class="form-label">Ежедневная викторина</label>
                                <div class="checkbox-item">
                                    <input type="checkbox" id="dailyQuizEnabled" ${chat.daily_quiz_enabled ? 'checked' : ''}>
                                    <label for="dailyQuizEnabled">Включить ежедневные викторины</label>
                                </div>
                            </div>
                            
                            <div class="form-group" id="dailyQuizTimesGroup">
                                <label class="form-label">Время запуска викторин (МСК)</label>
                                <div id="timesContainer">
                                    ${(chat.daily_quiz_times || []).map((time, idx) => `
                                        <div class="dynamic-field-item">
                                            <input type="time" class="form-input" value="${time}" required>
                                            <button type="button" class="btn-remove-field" onclick="removeTimeSlot(this)">×</button>
                                        </div>
                                    `).join('')}
                                </div>
                                <button type="button" class="btn-add-field" onclick="addTimeSlot()">+ Добавить время</button>
                                <p class="form-hint">Викторина будет автоматически запускаться в указанное время</p>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeModal('chatSettingsModal')">Отмена</button>
                        <button class="btn btn-primary" onclick="saveChatSettings('${chatId}')">Сохранить</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Toggle times visibility based on checkbox
        document.getElementById('dailyQuizEnabled').addEventListener('change', (e) => {
            document.getElementById('dailyQuizTimesGroup').style.display = e.target.checked ? 'block' : 'none';
        });
        
        // Initial visibility
        document.getElementById('dailyQuizTimesGroup').style.display = 
            chat.daily_quiz_enabled ? 'block' : 'none';
            
    } catch (error) {
        console.error('Error loading chat settings:', error);
        showToast('Ошибка загрузки настроек чата', 'error');
    }
}

// Add time slot
function addTimeSlot() {
    const container = document.getElementById('timesContainer');
    const html = `
        <div class="dynamic-field-item">
            <input type="time" class="form-input" value="09:00" required>
            <button type="button" class="btn-remove-field" onclick="removeTimeSlot(this)">×</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
}

// Remove time slot
function removeTimeSlot(button) {
    button.parentElement.remove();
}

// Save chat settings
async function saveChatSettings(chatId) {
    const enabled = document.getElementById('dailyQuizEnabled').checked;
    const timeInputs = document.querySelectorAll('#timesContainer input[type="time"]');
    const times = Array.from(timeInputs).map(input => input.value).filter(t => t);
    
    // Validation
    if (enabled && times.length === 0) {
        showToast('Добавьте хотя бы одно время запуска викторины', 'error');
        return;
    }
    
    const settings = {
        daily_quiz_enabled: enabled,
        daily_quiz_times: times
    };
    
    try {
        const response = await fetch(`/api/chats/${chatId}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showToast('Настройки чата сохранены', 'success');
            closeModal('chatSettingsModal');
            loadChats();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Ошибка сохранения настроек', 'error');
        }
    } catch (error) {
        console.error('Error saving chat settings:', error);
        showToast('Ошибка сохранения настроек', 'error');
    }
}
