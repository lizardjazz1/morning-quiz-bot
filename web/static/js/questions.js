// Questions Management Module
// Variables are defined in app.js

let currentEditingQuestion = null;
let currentPage = 1;
let itemsPerPage = 50;
let filteredQuestions = [];

// Load questions
async function loadQuestions() {
    try {
        const response = await fetch('/api/questions');
        const data = await response.json();

        allQuestions = data.questions || [];
        currentPage = 1; // Reset to first page
        displayQuestions(allQuestions);

        showToast(`Загружено ${allQuestions.length} вопросов`, 'success');
    } catch (error) {
        console.error('Error loading questions:', error);
        showToast('Ошибка загрузки вопросов', 'error');
    }
}

// Display questions
function displayQuestions(questions) {
    const container = document.getElementById('questionsContainer');

    filteredQuestions = questions;

    if (questions.length === 0) {
        container.innerHTML = '<p>Вопросы не найдены.</p>';
        return;
    }

    // Calculate pagination
    const totalPages = Math.ceil(questions.length / itemsPerPage);
    currentPage = Math.min(currentPage, totalPages); // Ensure current page is valid
    currentPage = Math.max(1, currentPage); // Ensure at least page 1

    const startIdx = (currentPage - 1) * itemsPerPage;
    const endIdx = startIdx + itemsPerPage;
    const pageQuestions = questions.slice(startIdx, endIdx);

    const html = `
        <div style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
            <div style="color: var(--text-secondary);">
                Показано ${startIdx + 1}-${Math.min(endIdx, questions.length)} из ${questions.length} вопросов
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <label style="font-size: 0.875rem; color: var(--text-secondary);">На странице:</label>
                <select class="form-select" style="width: auto; padding: 0.25rem 0.5rem;" onchange="changeItemsPerPage(this.value)">
                    <option value="25" ${itemsPerPage === 25 ? 'selected' : ''}>25</option>
                    <option value="50" ${itemsPerPage === 50 ? 'selected' : ''}>50</option>
                    <option value="100" ${itemsPerPage === 100 ? 'selected' : ''}>100</option>
                    <option value="200" ${itemsPerPage === 200 ? 'selected' : ''}>200</option>
                </select>
            </div>
        </div>

        <table class="data-table">
            <thead>
                <tr>
                    <th>Категория</th>
                    <th>Вопрос</th>
                    <th>Ответов</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                ${pageQuestions.map((q, relIdx) => {
                    const absoluteIdx = startIdx + relIdx;
                    return `
                    <tr>
                        <td><span style="background: var(--bg-secondary); padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.875rem;">${q.category}</span></td>
                        <td>${q.question.substring(0, 80)}${q.question.length > 80 ? '...' : ''}</td>
                        <td>${q.answers ? q.answers.length : 0}</td>
                        <td>
                            <div class="action-buttons">
                                <button class="btn btn-secondary btn-icon" onclick="viewQuestionByAbsoluteIndex(${absoluteIdx})" title="Просмотр">
                                    👁️
                                </button>
                                <button class="btn btn-primary btn-icon" onclick="editQuestionByAbsoluteIndex(${absoluteIdx})" title="Редактировать">
                                    ✏️
                                </button>
                                <button class="btn btn-danger btn-icon" onclick="deleteQuestionByAbsoluteIndex(${absoluteIdx})" title="Удалить">
                                    🗑️
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
                }).join('')}
            </tbody>
        </table>

        ${totalPages > 1 ? renderPagination(totalPages) : ''}
    `;

    container.innerHTML = html;
}

// Render pagination controls
function renderPagination(totalPages) {
    const maxButtons = 7; // Maximum number of page buttons to show
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);

    // Adjust start if we're near the end
    if (endPage - startPage < maxButtons - 1) {
        startPage = Math.max(1, endPage - maxButtons + 1);
    }

    let buttons = '';

    // Previous button
    buttons += `
        <button class="btn btn-secondary" onclick="goToPage(${currentPage - 1})"
                ${currentPage === 1 ? 'disabled' : ''}
                style="padding: 0.5rem 0.75rem;">
            ← Пред
        </button>
    `;

    // First page + ellipsis
    if (startPage > 1) {
        buttons += `<button class="btn btn-secondary" onclick="goToPage(1)" style="padding: 0.5rem 0.75rem;">1</button>`;
        if (startPage > 2) {
            buttons += `<span style="padding: 0.5rem; color: var(--text-secondary);">...</span>`;
        }
    }

    // Page numbers
    for (let i = startPage; i <= endPage; i++) {
        buttons += `
            <button class="btn ${i === currentPage ? 'btn-primary' : 'btn-secondary'}"
                    onclick="goToPage(${i})"
                    style="padding: 0.5rem 0.75rem;">
                ${i}
            </button>
        `;
    }

    // Last page + ellipsis
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            buttons += `<span style="padding: 0.5rem; color: var(--text-secondary);">...</span>`;
        }
        buttons += `<button class="btn btn-secondary" onclick="goToPage(${totalPages})" style="padding: 0.5rem 0.75rem;">${totalPages}</button>`;
    }

    // Next button
    buttons += `
        <button class="btn btn-secondary" onclick="goToPage(${currentPage + 1})"
                ${currentPage === totalPages ? 'disabled' : ''}
                style="padding: 0.5rem 0.75rem;">
            След →
        </button>
    `;

    return `
        <div style="margin-top: 1.5rem; display: flex; justify-content: center; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            ${buttons}
        </div>
    `;
}

// Pagination functions
function goToPage(page) {
    currentPage = page;
    displayQuestions(filteredQuestions);
}

function changeItemsPerPage(value) {
    itemsPerPage = parseInt(value);
    currentPage = 1; // Reset to first page
    displayQuestions(filteredQuestions);
}

// Filter questions
function filterQuestions() {
    const searchTerm = document.getElementById('questionSearch').value.toLowerCase();
    const filtered = allQuestions.filter(q =>
        q.question.toLowerCase().includes(searchTerm) ||
        q.category.toLowerCase().includes(searchTerm)
    );
    currentPage = 1; // Reset to first page on filter
    displayQuestions(filtered);
}

// Wrapper functions for absolute index access
function viewQuestionByAbsoluteIndex(idx) {
    const q = filteredQuestions[idx];
    const originalIdx = allQuestions.findIndex(question =>
        question.category === q.category &&
        question.question === q.question &&
        JSON.stringify(question.answers) === JSON.stringify(q.answers)
    );
    viewQuestion(originalIdx);
}

function editQuestionByAbsoluteIndex(idx) {
    const q = filteredQuestions[idx];
    const originalIdx = allQuestions.findIndex(question =>
        question.category === q.category &&
        question.question === q.question &&
        JSON.stringify(question.answers) === JSON.stringify(q.answers)
    );
    editQuestion(originalIdx);
}

function deleteQuestionByAbsoluteIndex(idx) {
    const q = filteredQuestions[idx];
    const originalIdx = allQuestions.findIndex(question =>
        question.category === q.category &&
        question.question === q.question &&
        JSON.stringify(question.answers) === JSON.stringify(q.answers)
    );
    deleteQuestion(originalIdx);
}

// View question
function viewQuestion(idx) {
    const q = allQuestions[idx];
    const modalHtml = `
        <div class="modal-overlay active" id="viewQuestionModal" onclick="closeModal('viewQuestionModal')">
            <div class="modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">Просмотр вопроса</h3>
                    <button class="modal-close" onclick="closeModal('viewQuestionModal')">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label class="form-label">Категория</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">${q.category}</div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Вопрос</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">${q.question}</div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Варианты ответов</label>
                        <ol style="margin: 0; padding-left: 1.5rem;">
                            ${q.answers.map((a, i) => `<li style="padding: 0.25rem 0; ${i === q.correct_answer ? 'color: var(--success); font-weight: 600;' : ''}">${a} ${i === q.correct_answer ? '✓' : ''}</li>`).join('')}
                        </ol>
                    </div>
                    ${q.explanation ? `
                    <div class="form-group">
                        <label class="form-label">Пояснение</label>
                        <div style="padding: 0.5rem; background: var(--bg-secondary); border-radius: 6px;">${q.explanation}</div>
                    </div>
                    ` : ''}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('viewQuestionModal')">Закрыть</button>
                    <button class="btn btn-primary" onclick="closeModal('viewQuestionModal'); editQuestion(${idx})">Редактировать</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Add new question
function addNewQuestion() {
    currentEditingQuestion = null;
    showQuestionModal();
}

// Edit question
function editQuestion(idx) {
    currentEditingQuestion = { ...allQuestions[idx], index: idx };
    showQuestionModal(currentEditingQuestion);
}

// Show question modal
function showQuestionModal(question = null) {
    const isEdit = question !== null;
    const modalHtml = `
        <div class="modal-overlay active" id="questionModal" onclick="closeModal('questionModal')">
            <div class="modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">${isEdit ? 'Редактировать вопрос' : 'Добавить вопрос'}</h3>
                    <button class="modal-close" onclick="closeModal('questionModal')">×</button>
                </div>
                <div class="modal-body">
                    <form id="questionForm">
                        <div class="form-group">
                            <label class="form-label required">Категория</label>
                            <input type="text" class="form-input" id="questionCategory" value="${question?.category || ''}" required list="categoriesList">
                            <datalist id="categoriesList">
                                <!-- Will be filled dynamically -->
                            </datalist>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label required">Вопрос</label>
                            <textarea class="form-textarea" id="questionText" required>${question?.question || ''}</textarea>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label required">Варианты ответов</label>
                            <div id="answersContainer">
                                ${(question?.answers || ['', '', '', '']).map((answer, i) => `
                                    <div class="dynamic-field-item">
                                        <input type="text" class="form-input" value="${answer}" placeholder="Вариант ${i + 1}" required>
                                        ${i > 1 ? '<button type="button" class="btn-remove-field" onclick="removeAnswer(this)">×</button>' : ''}
                                    </div>
                                `).join('')}
                            </div>
                            <button type="button" class="btn-add-field" onclick="addAnswer()">+ Добавить вариант</button>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label required">Правильный ответ</label>
                            <select class="form-select" id="correctAnswer" required>
                                ${(question?.answers || ['', '', '', '']).map((a, i) => `
                                    <option value="${i}" ${question?.correct_answer === i ? 'selected' : ''}>Вариант ${i + 1}${a ? ': ' + a : ''}</option>
                                `).join('')}
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Пояснение (необязательно)</label>
                            <textarea class="form-textarea" id="questionExplanation">${question?.explanation || ''}</textarea>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('questionModal')">Отмена</button>
                    <button class="btn btn-primary" onclick="saveQuestion()">${isEdit ? 'Сохранить' : 'Создать'}</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Load categories for datalist
    loadCategoriesForSelect();
}

// Add answer field
function addAnswer() {
    const container = document.getElementById('answersContainer');
    const count = container.querySelectorAll('.dynamic-field-item').length + 1;
    const html = `
        <div class="dynamic-field-item">
            <input type="text" class="form-input" placeholder="Вариант ${count}" required>
            <button type="button" class="btn-remove-field" onclick="removeAnswer(this)">×</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    updateCorrectAnswerOptions();
}

// Remove answer field
function removeAnswer(button) {
    button.parentElement.remove();
    updateCorrectAnswerOptions();
}

// Update correct answer options
function updateCorrectAnswerOptions() {
    const inputs = document.querySelectorAll('#answersContainer input');
    const select = document.getElementById('correctAnswer');
    const currentValue = select.value;
    
    select.innerHTML = Array.from(inputs).map((input, i) => 
        `<option value="${i}">Вариант ${i + 1}${input.value ? ': ' + input.value : ''}</option>`
    ).join('');
    
    if (currentValue < inputs.length) {
        select.value = currentValue;
    }
}

// Load categories for select
async function loadCategoriesForSelect() {
    try {
        const response = await fetch('/api/categories');
        const data = await response.json();
        const datalist = document.getElementById('categoriesList');
        if (datalist) {
            datalist.innerHTML = (data.categories || []).map(cat => 
                `<option value="${cat.name}">`
            ).join('');
        }
    } catch (error) {
        console.error('Error loading categories:', error);
    }
}

// Save question
async function saveQuestion() {
    const category = document.getElementById('questionCategory').value.trim();
    const question = document.getElementById('questionText').value.trim();
    const answerInputs = document.querySelectorAll('#answersContainer input');
    const answers = Array.from(answerInputs).map(input => input.value.trim());
    const correctAnswer = parseInt(document.getElementById('correctAnswer').value);
    const explanation = document.getElementById('questionExplanation').value.trim();
    
    // Validation
    if (!category || !question) {
        showToast('Заполните обязательные поля', 'error');
        return;
    }
    
    if (answers.length < 2) {
        showToast('Добавьте минимум 2 варианта ответа', 'error');
        return;
    }
    
    if (answers.some(a => !a)) {
        showToast('Заполните все варианты ответов', 'error');
        return;
    }
    
    const questionData = {
        category,
        question,
        answers,
        correct_answer: correctAnswer,
        explanation: explanation || null
    };
    
    try {
        let response;
        if (currentEditingQuestion) {
            // Update existing question
            response = await fetch(`/api/categories/${category}/questions/${currentEditingQuestion.index}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(questionData)
            });
        } else {
            // Create new question
            response = await fetch(`/api/categories/${category}/questions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(questionData)
            });
        }
        
        if (response.ok) {
            showToast(currentEditingQuestion ? 'Вопрос обновлен' : 'Вопрос создан', 'success');
            closeModal('questionModal');
            loadQuestions();
        } else {
            showToast('Ошибка сохранения вопроса', 'error');
        }
    } catch (error) {
        console.error('Error saving question:', error);
        showToast('Ошибка сохранения вопроса', 'error');
    }
}

// Delete question
function deleteQuestion(idx) {
    const q = allQuestions[idx];
    const modalHtml = `
        <div class="modal-overlay active" id="deleteModal" onclick="closeModal('deleteModal')">
            <div class="modal confirm-dialog" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title">Подтверждение удаления</h3>
                    <button class="modal-close" onclick="closeModal('deleteModal')">×</button>
                </div>
                <div class="modal-body">
                    <p class="confirm-message">Вы уверены, что хотите удалить этот вопрос?</p>
                    <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; margin-top: 1rem;">
                        <strong>Вопрос:</strong> ${q.question}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeModal('deleteModal')">Отмена</button>
                    <button class="btn btn-danger" onclick="confirmDeleteQuestion('${q.category}', ${idx})">Удалить</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// Confirm delete question
async function confirmDeleteQuestion(category, idx) {
    try {
        const response = await fetch(`/api/categories/${category}/questions/${idx}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Вопрос удален', 'success');
            closeModal('deleteModal');
            loadQuestions();
        } else {
            showToast('Ошибка удаления вопроса', 'error');
        }
    } catch (error) {
        console.error('Error deleting question:', error);
        showToast('Ошибка удаления вопроса', 'error');
    }
}
