// Photo Quiz Management Module
// Variables are defined in app.js

// Load photo quiz
async function loadPhotoQuiz() {
    try {
        const response = await fetch('/api/photo-quiz');
        const data = await response.json();
        
        allPhotoQuizImages = data.images || [];
        displayPhotoQuiz(allPhotoQuizImages);
        
        showToast(`Загружено ${allPhotoQuizImages.length} изображений`, 'success');
    } catch (error) {
        console.error('Error loading photo quiz:', error);
        showToast('Ошибка загрузки фото-викторин', 'error');
    }
}

// Display photo quiz
function displayPhotoQuiz(images) {
    const container = document.getElementById('photoQuizContainer');
    
    if (images.length === 0) {
        container.innerHTML = '<p>Изображения не найдены.</p>';
        return;
    }
    
    const html = `
        <div class="photo-grid">
            ${images.map((img, idx) => `
                <div class="photo-card">
                    <div class="photo-image" style="background-image: url('/api/images/${img.filename}');" onclick="viewPhotoDetails(${idx})">
                        ${!img.filename ? '<div style="display: flex; align-items: center; justify-content: center; height: 100%; background: var(--bg-secondary); color: var(--text-secondary);">🖼️<br>Нет изображения</div>' : ''}
                    </div>
                    <div class="photo-info">
                        <div class="photo-title">${img.title || 'Без названия'}</div>
                        <div class="photo-answer">✓ ${img.correct_answer}</div>
                    </div>
                    <div class="photo-actions">
                        <button class="btn btn-secondary btn-icon" onclick="viewPhotoDetails(${idx})" title="Просмотр">
                            👁️
                        </button>
                        <button class="btn btn-primary btn-icon" onclick="editPhotoQuiz(${idx})" title="Редактировать">
                            ✏️
                        </button>
                        <button class="btn btn-danger btn-icon" onclick="deletePhotoQuiz(${idx})" title="Удалить">
                            🗑️
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    container.innerHTML = html;
}

// View photo details
function viewPhotoDetails(idx) {
    const img = allPhotoQuizImages[idx];
    const modalHtml = `
        <div class="modal-overlay active" id="photoDetailsModal" onclick="closeModal('photoDetailsModal')">
            <div class="modal" onclick="event.stopPropagation()" style="max-width: 700px;">
                <div class="modal-header">
                    <h3 class="modal-title">Просмотр фото-викторины</h3>
                    <button class="modal-close" onclick="closeModal('photoDetailsModal')">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Изображение</label>
                        <div style="width: 100%; height: 300px; background: var(--bg-secondary); border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center;">
                            ${img.filename ? 
                                `<img src="/api/images/${img.filename}" style="width: 100%; height: 100%; object-fit: contain;">` : 
                                '<span style="color: var(--text-secondary);">🖼️ Изображение недоступно</span>'
                            }
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Название</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">${img.title || 'Без названия'}</div>
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label">Правильный ответ</label>
                        <div style="padding: 0.5rem; background: var(--success); color: white; border-radius: 6px; font-weight: 600;">✓ ${img.correct_answer}</div>
                    </div>
                    
                    ${img.alt_answers && img.alt_answers.length > 0 ? `
                    <div class="form-group">
                        <label class="form-label">Альтернативные ответы</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">
                            ${img.alt_answers.join(', ')}
                        </div>
                    </div>
                    ` : ''}
                    
                    <div class="form-group">
                        <label class="form-label">Файл</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px; font-family: monospace; font-size: 0.875rem;">${img.filename || 'Нет файла'}</div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('photoDetailsModal')">Закрыть</button>
                    <button class="btn btn-primary" onclick="closeModal('photoDetailsModal'); editPhotoQuiz(${idx})">Редактировать</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Add new photo quiz
function addNewPhotoQuiz() {
    showPhotoQuizModal();
}

// Edit photo quiz
function editPhotoQuiz(idx) {
    const photo = allPhotoQuizImages[idx];
    showPhotoQuizModal({ ...photo, index: idx });
}

// Show photo quiz modal
function showPhotoQuizModal(photo = null) {
    const isEdit = photo !== null;
    const modalHtml = `
        <div class="modal-overlay active" id="photoQuizModal" onclick="closeModal('photoQuizModal')">
            <div class="modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">${isEdit ? 'Редактировать фото-викторину' : 'Добавить фото-викторину'}</h3>
                    <button class="modal-close" onclick="closeModal('photoQuizModal')">×</button>
                </div>
                <div class="modal-body">
                    <form id="photoQuizForm">
                        ${isEdit && photo.filename ? `
                        <div class="form-group">
                            <label class="form-label">Текущее изображение</label>
                            <div style="width: 100%; height: 200px; background: var(--bg-secondary); border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center;">
                                <img src="/api/images/${photo.filename}" style="width: 100%; height: 100%; object-fit: contain;">
                            </div>
                        </div>
                        ` : ''}
                        
                        <div class="form-group">
                            <label class="form-label ${!isEdit ? 'required' : ''}">Изображение</label>
                            <div class="file-upload-area" id="fileUploadArea">
                                <div class="file-upload-icon">📁</div>
                                <div class="file-upload-text">
                                    <strong>Нажмите для выбора</strong> или перетащите файл сюда<br>
                                    <span style="font-size: 0.75rem;">Поддерживаемые форматы: JPG, PNG, GIF</span>
                                </div>
                                <input type="file" id="photoFile" accept="image/*" style="display: none;" ${!isEdit ? 'required' : ''}>
                            </div>
                            <div id="filePreview" class="file-preview" style="display: none;"></div>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Название</label>
                            <input type="text" class="form-input" id="photoTitle" value="${photo?.title || ''}" placeholder="Краткое описание">
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label required">Правильный ответ</label>
                            <input type="text" class="form-input" id="photoCorrectAnswer" value="${photo?.correct_answer || ''}" required placeholder="Что изображено на фото?">
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Альтернативные ответы</label>
                            <div id="altAnswersContainer">
                                ${(photo?.alt_answers || []).map((answer, i) => `
                                    <div class="dynamic-field-item">
                                        <input type="text" class="form-input" value="${answer}" placeholder="Альтернативный ответ">
                                        <button type="button" class="btn-remove-field" onclick="removeAltAnswer(this)">×</button>
                                    </div>
                                `).join('')}
                            </div>
                            <button type="button" class="btn-add-field" onclick="addAltAnswer()">+ Добавить вариант</button>
                            <p class="form-hint">Другие правильные варианты ответа</p>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('photoQuizModal')">Отмена</button>
                    <button class="btn btn-primary" onclick="savePhotoQuiz(${isEdit ? photo.index : 'null'})">${isEdit ? 'Сохранить' : 'Создать'}</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Setup file upload
    setupFileUpload();
}

// Setup file upload
function setupFileUpload() {
    const area = document.getElementById('fileUploadArea');
    const input = document.getElementById('photoFile');
    const preview = document.getElementById('filePreview');
    
    area.addEventListener('click', () => input.click());
    
    input.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            showFilePreview(file);
        }
    });
    
    // Drag and drop
    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.classList.add('dragover');
    });
    
    area.addEventListener('dragleave', () => {
        area.classList.remove('dragover');
    });
    
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            input.files = e.dataTransfer.files;
            showFilePreview(file);
        }
    });
}

// Show file preview
function showFilePreview(file) {
    const preview = document.getElementById('filePreview');
    const reader = new FileReader();
    
    reader.onload = (e) => {
        preview.innerHTML = `
            <img src="${e.target.result}">
            <div>
                <div style="font-weight: 600;">${file.name}</div>
                <div style="font-size: 0.875rem; color: var(--text-secondary);">${(file.size / 1024).toFixed(1)} KB</div>
            </div>
            <button type="button" class="btn btn-secondary btn-icon" onclick="clearFileUpload()">×</button>
        `;
        preview.style.display = 'flex';
    };
    
    reader.readAsDataURL(file);
}

// Clear file upload
function clearFileUpload() {
    document.getElementById('photoFile').value = '';
    document.getElementById('filePreview').style.display = 'none';
}

// Add alt answer
function addAltAnswer() {
    const container = document.getElementById('altAnswersContainer');
    const html = `
        <div class="dynamic-field-item">
            <input type="text" class="form-input" placeholder="Альтернативный ответ">
            <button type="button" class="btn-remove-field" onclick="removeAltAnswer(this)">×</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
}

// Remove alt answer
function removeAltAnswer(button) {
    button.parentElement.remove();
}

// Save photo quiz
async function savePhotoQuiz(idx) {
    const title = document.getElementById('photoTitle').value.trim();
    const correctAnswer = document.getElementById('photoCorrectAnswer').value.trim();
    const fileInput = document.getElementById('photoFile');
    const altAnswerInputs = document.querySelectorAll('#altAnswersContainer input');
    const altAnswers = Array.from(altAnswerInputs).map(input => input.value.trim()).filter(a => a);
    
    // Validation
    if (!correctAnswer) {
        showToast('Укажите правильный ответ', 'error');
        return;
    }
    
    if (idx === null && !fileInput.files[0]) {
        showToast('Выберите изображение', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('title', title);
    formData.append('correct_answer', correctAnswer);
    formData.append('alt_answers', JSON.stringify(altAnswers));
    
    if (fileInput.files[0]) {
        formData.append('image', fileInput.files[0]);
    }
    
    try {
        let response;
        if (idx !== null) {
            // Update
            response = await fetch(`/api/photo-quiz/${idx}`, {
                method: 'PUT',
                body: formData
            });
        } else {
            // Create
            response = await fetch('/api/photo-quiz', {
                method: 'POST',
                body: formData
            });
        }
        
        if (response.ok) {
            showToast(idx !== null ? 'Фото-викторина обновлена' : 'Фото-викторина создана', 'success');
            closeModal('photoQuizModal');
            loadPhotoQuiz();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Ошибка сохранения', 'error');
        }
    } catch (error) {
        console.error('Error saving photo quiz:', error);
        showToast('Ошибка сохранения фото-викторины', 'error');
    }
}

// Delete photo quiz
function deletePhotoQuiz(idx) {
    const photo = allPhotoQuizImages[idx];
    const modalHtml = `
        <div class="modal-overlay active" id="deletePhotoModal" onclick="closeModal('deletePhotoModal')">
            <div class="modal confirm-dialog" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">Подтверждение удаления</h3>
                    <button class="modal-close" onclick="closeModal('deletePhotoModal')">×</button>
                </div>
                <div class="modal-body">
                    <p class="confirm-message">Вы уверены, что хотите удалить эту фото-викторину?</p>
                    <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; margin-top: 1rem; text-align: center;">
                        ${photo.filename ? 
                            `<img src="/api/images/${photo.filename}" style="max-width: 200px; max-height: 150px; border-radius: 6px; margin-bottom: 0.5rem;">` : 
                            '<div style="font-size: 3rem;">🖼️</div>'
                        }
                        <div><strong>${photo.title || 'Без названия'}</strong></div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary);">${photo.correct_answer}</div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('deletePhotoModal')">Отмена</button>
                    <button class="btn btn-danger" onclick="confirmDeletePhotoQuiz(${idx})">Удалить</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Confirm delete photo quiz
async function confirmDeletePhotoQuiz(idx) {
    try {
        const response = await fetch(`/api/photo-quiz/${idx}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Фото-викторина удалена', 'success');
            closeModal('deletePhotoModal');
            loadPhotoQuiz();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Ошибка удаления', 'error');
        }
    } catch (error) {
        console.error('Error deleting photo quiz:', error);
        showToast('Ошибка удаления фото-викторины', 'error');
    }
}
