// Categories Management Module
// Variables are defined in app.js

// Load categories
async function loadCategories() {
    try {
        const response = await fetch('/api/categories');
        const data = await response.json();
        
        allCategories = data.categories || [];
        displayCategories(allCategories);
        
        showToast(`Загружено ${allCategories.length} категорий`, 'success');
    } catch (error) {
        console.error('Error loading categories:', error);
        showToast('Ошибка загрузки категорий', 'error');
    }
}

// Display categories
function displayCategories(categories) {
    const container = document.getElementById('categoriesContainer');
    
    if (categories.length === 0) {
        container.innerHTML = '<p>Категории не найдены.</p>';
        return;
    }
    
    const html = categories.map(cat => `
        <div class="stat-card">
            <div class="stat-header">
                <div>
                    <div class="stat-title">${cat.name}</div>
                    <div class="stat-subtitle">${cat.question_count || 0} вопросов</div>
                </div>
                <div class="stat-icon">📁</div>
            </div>
            <div class="stat-body" style="margin-top: 1rem;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: var(--text-secondary); font-size: 0.875rem;">Использована:</span>
                    <strong>${cat.times_used || 0} раз</strong>
                </div>
                ${cat.description ? `
                <div style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px; font-size: 0.875rem;">
                    ${cat.description}
                </div>
                ` : ''}
            </div>
            <div class="stat-footer" style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                <button class="btn btn-secondary" style="flex: 1; font-size: 0.875rem;" onclick="viewCategoryQuestions('${cat.name}')">
                    📝 Вопросы
                </button>
                <button class="btn btn-primary btn-icon" onclick="editCategory('${cat.name}')">
                    ✏️
                </button>
                <button class="btn btn-danger btn-icon" onclick="deleteCategory('${cat.name}')">
                    🗑️
                </button>
            </div>
        </div>
    `).join('');
    
    container.innerHTML = html;
}

// View category questions
async function viewCategoryQuestions(categoryName) {
    try {
        const response = await fetch(`/api/categories/${categoryName}/questions`);
        if (!response.ok) throw new Error('Failed to load questions');
        
        const data = await response.json();
        const questions = data.questions || [];
        
        const modalHtml = `
            <div class="modal-overlay active" id="categoryQuestionsModal" onclick="closeModal('categoryQuestionsModal')">
                <div class="modal" onclick="event.stopPropagation()" style="max-width: 800px;">
                    <div class="modal-header">
                        <h3 class="modal-title">Вопросы категории "${categoryName}"</h3>
                        <button class="modal-close" onclick="closeModal('categoryQuestionsModal')">×</button>
                    </div>
                    <div class="modal-body">
                        ${questions.length === 0 ? '<p>В этой категории пока нет вопросов.</p>' : `
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>Вопрос</th>
                                        <th>Ответов</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${questions.map((q, idx) => `
                                        <tr>
                                            <td>${idx + 1}</td>
                                            <td>${q.question.substring(0, 60)}${q.question.length > 60 ? '...' : ''}</td>
                                            <td>${q.answers?.length || 0}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `}
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-secondary" onclick="closeModal('categoryQuestionsModal')">Закрыть</button>
                        <button class="btn btn-primary" onclick="closeModal('categoryQuestionsModal'); showSection('questions')">Перейти к вопросам</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (error) {
        console.error('Error loading category questions:', error);
        showToast('Ошибка загрузки вопросов категории', 'error');
    }
}

// Add new category
function addNewCategory() {
    showCategoryModal();
}

// Edit category
async function editCategory(categoryName) {
    try {
        const response = await fetch(`/api/categories/${categoryName}`);
        if (!response.ok) throw new Error('Failed to load category');
        
        const category = await response.json();
        showCategoryModal(category);
    } catch (error) {
        console.error('Error loading category:', error);
        showToast('Ошибка загрузки категории', 'error');
    }
}

// Show category modal
function showCategoryModal(category = null) {
    const isEdit = category !== null;
    const modalHtml = `
        <div class="modal-overlay active" id="categoryModal" onclick="closeModal('categoryModal')">
            <div class="modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">${isEdit ? 'Редактировать категорию' : 'Добавить категорию'}</h3>
                    <button class="modal-close" onclick="closeModal('categoryModal')">×</button>
                </div>
                <div class="modal-body">
                    <form id="categoryForm">
                        <div class="form-group">
                            <label class="form-label required">Название категории</label>
                            <input type="text" class="form-input" id="categoryName" value="${category?.name || ''}" required ${isEdit ? 'readonly style="background: var(--bg-secondary);"' : ''}>
                            ${isEdit ? '<p class="form-hint">Название категории нельзя изменить</p>' : ''}
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Описание</label>
                            <textarea class="form-textarea" id="categoryDescription">${category?.description || ''}</textarea>
                            <p class="form-hint">Краткое описание категории</p>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('categoryModal')">Отмена</button>
                    <button class="btn btn-primary" onclick="saveCategory(${isEdit})">${isEdit ? 'Сохранить' : 'Создать'}</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Save category
async function saveCategory(isEdit) {
    const name = document.getElementById('categoryName').value.trim();
    const description = document.getElementById('categoryDescription').value.trim();
    
    if (!name) {
        showToast('Введите название категории', 'error');
        return;
    }
    
    const categoryData = {
        name,
        description: description || ''
    };
    
    try {
        let response;
        if (isEdit) {
            response = await fetch(`/api/categories/${name}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(categoryData)
            });
        } else {
            response = await fetch('/api/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(categoryData)
            });
        }
        
        if (response.ok) {
            showToast(isEdit ? 'Категория обновлена' : 'Категория создана', 'success');
            closeModal('categoryModal');
            loadCategories();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Ошибка сохранения категории', 'error');
        }
    } catch (error) {
        console.error('Error saving category:', error);
        showToast('Ошибка сохранения категории', 'error');
    }
}

// Delete category
function deleteCategory(categoryName) {
    const category = allCategories.find(c => c.name === categoryName);
    const questionCount = category?.question_count || 0;
    
    const modalHtml = `
        <div class="modal-overlay active" id="deleteCategoryModal" onclick="closeModal('deleteCategoryModal')">
            <div class="modal confirm-dialog" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">Подтверждение удаления</h3>
                    <button class="modal-close" onclick="closeModal('deleteCategoryModal')">×</button>
                </div>
                <div class="modal-body">
                    <p class="confirm-message">Вы уверены, что хотите удалить категорию "${categoryName}"?</p>
                    ${questionCount > 0 ? `
                        <div style="padding: 0.75rem; background: rgba(239, 68, 68, 0.1); border: 1px solid var(--danger); border-radius: 8px; margin-top: 1rem;">
                            <strong style="color: var(--danger);">⚠️ Внимание!</strong><br>
                            <span style="font-size: 0.875rem;">В этой категории ${questionCount} вопросов. Они также будут удалены!</span>
                        </div>
                    ` : ''}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('deleteCategoryModal')">Отмена</button>
                    <button class="btn btn-danger" onclick="confirmDeleteCategory('${categoryName}')">Удалить</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Confirm delete category
async function confirmDeleteCategory(categoryName) {
    try {
        const response = await fetch(`/api/categories/${categoryName}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Категория удалена', 'success');
            closeModal('deleteCategoryModal');
            loadCategories();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Ошибка удаления категории', 'error');
        }
    } catch (error) {
        console.error('Error deleting category:', error);
        showToast('Ошибка удаления категории', 'error');
    }
}
