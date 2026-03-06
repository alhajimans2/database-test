// ===========================================================
// Core UI interactions
// ===========================================================
document.addEventListener('DOMContentLoaded', () => {
    setupThemeToggle();
    setupSidebar();
    setupCommandBar();
    setupMultiStepForm();
    setupAutoDismissAlerts();
    setupAnimatedStatCounters();
    setupFinanceCalculation();
    setupDraftAutosave();
});

function setupFinanceCalculation() {
    const tuitionInput = document.getElementById('finance_tuition_fee');
    const registrationInput = document.getElementById('finance_registration_fee');
    const examInput = document.getElementById('finance_exam_fee');
    const libraryIctInput = document.getElementById('finance_library_ict_fee');
    const labInput = document.getElementById('finance_lab_practical_fee');
    const accommodationInput = document.getElementById('finance_accommodation_fee');
    const miscellaneousInput = document.getElementById('finance_miscellaneous_fee');
    const scholarshipInput = document.getElementById('finance_scholarship_discount');
    const fullCostInput = document.getElementById('finance_full_cost');
    const amountPaidInput = document.getElementById('finance_amount_paid');
    const otherCommitmentsInput = document.getElementById('finance_other_commitments');
    const outstandingInput = document.getElementById('finance_outstanding');

    if (!fullCostInput || !amountPaidInput || !otherCommitmentsInput || !outstandingInput) return;

    const parseMoney = (value) => {
        const number = Number(value);
        if (!Number.isFinite(number) || number < 0) return 0;
        return number;
    };

    const recalculateOutstanding = () => {
        const grossCost =
            parseMoney(tuitionInput?.value)
            + parseMoney(registrationInput?.value)
            + parseMoney(examInput?.value)
            + parseMoney(libraryIctInput?.value)
            + parseMoney(labInput?.value)
            + parseMoney(accommodationInput?.value)
            + parseMoney(miscellaneousInput?.value);
        const scholarship = parseMoney(scholarshipInput?.value);
        const fullCost = Math.max(grossCost - scholarship, 0);
        const amountPaid = parseMoney(amountPaidInput.value);
        const commitments = parseMoney(otherCommitmentsInput.value);
        const outstanding = (fullCost + commitments) - amountPaid;
        fullCostInput.value = fullCost.toFixed(2);
        outstandingInput.value = Math.max(outstanding, 0).toFixed(2);
    };

    [
        tuitionInput,
        registrationInput,
        examInput,
        libraryIctInput,
        labInput,
        accommodationInput,
        miscellaneousInput,
        scholarshipInput,
        amountPaidInput,
        otherCommitmentsInput,
    ].filter(Boolean).forEach(input => {
        input.addEventListener('input', recalculateOutstanding);
        input.addEventListener('change', recalculateOutstanding);
    });

    recalculateOutstanding();
}

function setupThemeToggle() {
    const toggleButtons = document.querySelectorAll('#themeToggle, .theme-toggle-js');
    const themeKey = 'tit_theme_preference';

    function applyTheme(theme) {
        const isDark = theme === 'dark';
        document.body.classList.toggle('theme-dark', isDark);

        toggleButtons.forEach(toggleButton => {
            const icon = toggleButton.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-moon', !isDark);
                icon.classList.toggle('fa-sun', isDark);
            }
            toggleButton.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
            toggleButton.setAttribute('title', isDark ? 'Switch to light mode' : 'Switch to dark mode');
        });
    }

    const savedTheme = localStorage.getItem(themeKey);
    const serverThemeDefault = document.body.getAttribute('data-theme-default') || 'system';
    const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const preferredTheme = savedTheme || serverThemeDefault;
    const initialTheme = preferredTheme === 'system' ? (systemPrefersDark ? 'dark' : 'light') : preferredTheme;
    applyTheme(initialTheme);

    toggleButtons.forEach(toggleButton => {
        toggleButton.addEventListener('click', () => {
            const nextTheme = document.body.classList.contains('theme-dark') ? 'light' : 'dark';
            localStorage.setItem(themeKey, nextTheme);
            applyTheme(nextTheme);
        });
    });
}

function setupAnimatedStatCounters() {
    const counters = document.querySelectorAll('.stat-counter[data-target]');
    if (!counters.length) return;

    const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) return;

    counters.forEach(counter => {
        const target = Number(counter.dataset.target || 0);
        const suffix = counter.dataset.suffix || '';
        const duration = 900;
        const start = performance.now();

        function update(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = Math.round(target * eased);
            counter.textContent = `${value}${suffix}`;

            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }

        counter.textContent = `0${suffix}`;
        requestAnimationFrame(update);
    });
}

function setupSidebar() {
    const sidebar = document.getElementById('sidebar');
    const hamburger = document.getElementById('hamburger');
    const sidebarClose = document.getElementById('sidebarClose');

    if (!sidebar) return;

    if (hamburger) {
        hamburger.addEventListener('click', () => {
            sidebar.classList.add('open');
        });
    }

    if (sidebarClose) {
        sidebarClose.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }

    // close sidebar on click outside (mobile)
    document.addEventListener('click', (event) => {
        if (window.innerWidth > 992 || !sidebar.classList.contains('open')) return;
        const isInsideSidebar = sidebar.contains(event.target);
        const isHamburger = hamburger && hamburger.contains(event.target);
        if (!isInsideSidebar && !isHamburger) {
            sidebar.classList.remove('open');
        }
    });
}

function setupCommandBar() {
    const commandBar = document.getElementById('commandBar');
    const commandBarToggle = document.getElementById('commandBarToggle');
    const commandBarClose = document.getElementById('commandBarClose');
    const commandInput = document.getElementById('commandSearchInput');
    const results = document.getElementById('commandSearchResults');

    if (!commandBar || !commandInput || !results) return;

    const commands = [
        { label: 'Dashboard', href: '/dashboard', keywords: ['home', 'overview', 'dashboard'] },
        { label: 'All Students', href: '/students', keywords: ['students', 'records', 'list'] },
        { label: 'Register Student', href: '/students/add', keywords: ['add', 'register', 'new'] },
        { label: 'Reports', href: '/reports', keywords: ['reports', 'analytics', 'defaulters'] },
        { label: 'Recycle Bin', href: '/students/recycle-bin', keywords: ['recycle', 'archived', 'restore'] },
        { label: 'Audit Logs', href: '/governance/audit-logs', keywords: ['audit', 'logs', 'governance'] },
        { label: 'Settings', href: '/settings', keywords: ['settings', 'preferences'] },
    ];

    const renderResults = (query = '') => {
        const term = query.trim().toLowerCase();
        const filtered = commands.filter(item => {
            if (!term) return true;
            return item.label.toLowerCase().includes(term) || item.keywords.some(keyword => keyword.includes(term));
        });

        results.innerHTML = filtered.map(item => (
            `<a class="quick-action-btn" href="${item.href}"><i class="fas fa-arrow-right"></i><span>${item.label}</span></a>`
        )).join('') || '<p class="text-muted">No matching command.</p>';
    };

    const openBar = () => {
        commandBar.classList.add('open');
        renderResults(commandInput.value);
        setTimeout(() => commandInput.focus(), 20);
    };

    const closeBar = () => {
        commandBar.classList.remove('open');
    };

    commandBarToggle?.addEventListener('click', openBar);
    commandBarClose?.addEventListener('click', closeBar);

    commandInput.addEventListener('input', () => renderResults(commandInput.value));
    commandBar.addEventListener('click', (event) => {
        if (event.target === commandBar) closeBar();
    });

    document.addEventListener('keydown', (event) => {
        const pressedK = event.key.toLowerCase() === 'k';
        if ((event.ctrlKey || event.metaKey) && pressedK) {
            event.preventDefault();
            openBar();
        }
        if (event.key === 'Escape' && commandBar.classList.contains('open')) {
            closeBar();
        }
    });
}

function setupAutoDismissAlerts() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (!alert.parentNode) return;
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-4px)';
            setTimeout(() => {
                if (alert.parentNode) alert.remove();
            }, 250);
        }, 5000);
    });
}

// ===========================================================
// Multi-step student form logic
// ===========================================================
function setupMultiStepForm() {
    const form = document.getElementById('studentForm');
    if (!form) return;

    const sections = document.querySelectorAll('.form-section');
    const progressSteps = document.querySelectorAll('.progress-step');

    function showStep(step) {
        sections.forEach(section => section.classList.remove('active'));
        progressSteps.forEach(progress => progress.classList.remove('active'));

        const targetSection = document.getElementById(`step-${step}`);
        if (targetSection) {
            targetSection.classList.add('active');
            targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        progressSteps.forEach((progress, index) => {
            if (index + 1 <= step) progress.classList.add('active');
        });
    }

    document.querySelectorAll('.btn-next').forEach(btn => {
        btn.addEventListener('click', () => {
            const nextStep = Number(btn.getAttribute('data-next'));
            if (!nextStep) return;

            const currentSection = btn.closest('.form-section');
            if (!validateSection(currentSection)) return;

            showStep(nextStep);
        });
    });

    document.querySelectorAll('.btn-prev').forEach(btn => {
        btn.addEventListener('click', () => {
            const prevStep = Number(btn.getAttribute('data-prev'));
            if (!prevStep) return;
            showStep(prevStep);
        });
    });

    progressSteps.forEach(step => {
        step.addEventListener('click', () => {
            const stepNumber = Number(step.getAttribute('data-step'));
            if (!stepNumber) return;
            showStep(stepNumber);
        });
    });

    showStep(1);
}

function validateSection(section) {
    if (!section) return true;
    const requiredFields = section.querySelectorAll('[required]');

    let isValid = true;
    requiredFields.forEach(field => {
        if (!field.value || !field.value.trim()) {
            field.style.borderColor = '#ef4444';
            field.style.boxShadow = '0 0 0 3px rgba(239,68,68,0.15)';
            isValid = false;
        } else {
            field.style.borderColor = '';
            field.style.boxShadow = '';
        }
    });

    if (!isValid) {
        const firstInvalid = section.querySelector('[required][style*="ef4444"]') || section.querySelector('[required]:invalid');
        if (firstInvalid) firstInvalid.focus();
        alert('Please fill in all required fields before continuing.');
    }

    return isValid;
}

// ===========================================================
// Dynamic rows: Education / Work / Parents
// ===========================================================
function removeRow(button) {
    const row = button.closest('.dynamic-row');
    if (!row) return;
    const container = row.parentElement;
    const allRows = container.querySelectorAll('.dynamic-row');

    if (allRows.length <= 1) {
        clearDynamicRow(row);
        return;
    }

    row.remove();
    renumberRows(container);
}

function clearDynamicRow(row) {
    row.querySelectorAll('input, textarea, select').forEach(input => {
        if (input.tagName === 'SELECT') {
            input.selectedIndex = 0;
        } else {
            input.value = '';
        }
    });
}

function renumberRows(container) {
    const rows = container.querySelectorAll('.dynamic-row');
    rows.forEach((row, index) => {
        const heading = row.querySelector('.row-header h4');
        if (!heading) return;
        if (row.classList.contains('education-row')) heading.textContent = `Education Record #${index + 1}`;
        if (row.classList.contains('work-row')) heading.textContent = `Work Record #${index + 1}`;
        if (row.classList.contains('parent-row')) heading.textContent = `Parent / Guardian #${index + 1}`;
    });
}

function addEducationRow() {
    const container = document.getElementById('educationRows');
    if (!container) return;

    const div = document.createElement('div');
    div.className = 'dynamic-row education-row';
    div.innerHTML = `
        <div class="row-header">
            <h4>Education Record #${container.querySelectorAll('.education-row').length + 1}</h4>
            <button type="button" class="btn-remove" onclick="removeRow(this)" title="Remove"><i class="fas fa-trash"></i></button>
        </div>
        <div class="form-grid">
            <div class="form-group">
                <label>Institution Name</label>
                <input type="text" name="edu_institution[]" placeholder="e.g. Harare High School">
            </div>
            <div class="form-group">
                <label>Level</label>
                <select name="edu_level[]">
                    <option value="">Select Level</option>
                    <option value="Primary">Primary</option>
                    <option value="O-Level">O-Level (Secondary)</option>
                    <option value="A-Level">A-Level</option>
                    <option value="Certificate">Certificate</option>
                    <option value="Diploma">Diploma</option>
                    <option value="Higher National Diploma">Higher National Diploma</option>
                    <option value="Bachelor's Degree">Bachelor's Degree</option>
                    <option value="Master's Degree">Master's Degree</option>
                    <option value="Doctorate">Doctorate</option>
                </select>
            </div>
            <div class="form-group">
                <label>Qualification Obtained</label>
                <input type="text" name="edu_qualification[]" placeholder="e.g. O-Level Certificate">
            </div>
            <div class="form-group">
                <label>Field of Study</label>
                <input type="text" name="edu_field[]" placeholder="e.g. Sciences">
            </div>
            <div class="form-group">
                <label>Start Date</label>
                <input type="date" name="edu_start[]">
            </div>
            <div class="form-group">
                <label>End Date</label>
                <input type="date" name="edu_end[]">
            </div>
            <div class="form-group">
                <label>Grade / GPA</label>
                <input type="text" name="edu_grade[]" placeholder="e.g. 10 Points / 3.5 GPA">
            </div>
            <div class="form-group">
                <label>Country</label>
                <input type="text" name="edu_country[]" value="Zimbabwe" placeholder="Country">
            </div>
        </div>
    `;

    container.appendChild(div);
}

function addWorkRow() {
    const container = document.getElementById('workRows');
    if (!container) return;

    const div = document.createElement('div');
    div.className = 'dynamic-row work-row';
    div.innerHTML = `
        <div class="row-header">
            <h4>Work Record #${container.querySelectorAll('.work-row').length + 1}</h4>
            <button type="button" class="btn-remove" onclick="removeRow(this)" title="Remove"><i class="fas fa-trash"></i></button>
        </div>
        <div class="form-grid">
            <div class="form-group">
                <label>Company / Organisation</label>
                <input type="text" name="work_company[]" placeholder="Company name">
            </div>
            <div class="form-group">
                <label>Job Title / Position</label>
                <input type="text" name="work_title[]" placeholder="e.g. Junior Developer">
            </div>
            <div class="form-group">
                <label>Employment Type</label>
                <select name="work_type[]">
                    <option value="">Select</option>
                    <option value="Full-time">Full-time</option>
                    <option value="Part-time">Part-time</option>
                    <option value="Internship">Internship</option>
                    <option value="Contract">Contract</option>
                    <option value="Volunteer">Volunteer</option>
                </select>
            </div>
            <div class="form-group">
                <label>Start Date</label>
                <input type="date" name="work_start[]">
            </div>
            <div class="form-group">
                <label>End Date</label>
                <input type="date" name="work_end[]">
            </div>
            <div class="form-group">
                <label>Country</label>
                <input type="text" name="work_country[]" value="Zimbabwe" placeholder="Country">
            </div>
            <div class="form-group full-width">
                <label>Responsibilities / Duties</label>
                <textarea name="work_responsibilities[]" rows="2" placeholder="Describe your responsibilities"></textarea>
            </div>
        </div>
    `;

    container.appendChild(div);
}

function addParentRow() {
    const container = document.getElementById('parentRows');
    if (!container) return;

    const div = document.createElement('div');
    div.className = 'dynamic-row parent-row';
    div.innerHTML = `
        <div class="row-header">
            <h4>Parent / Guardian #${container.querySelectorAll('.parent-row').length + 1}</h4>
            <button type="button" class="btn-remove" onclick="removeRow(this)" title="Remove"><i class="fas fa-trash"></i></button>
        </div>
        <div class="form-grid">
            <div class="form-group">
                <label>Relationship</label>
                <select name="parent_relationship[]">
                    <option value="Father">Father</option>
                    <option value="Mother">Mother</option>
                    <option value="Guardian">Guardian</option>
                    <option value="Sponsor">Sponsor</option>
                </select>
            </div>
            <div class="form-group">
                <label>First Name</label>
                <input type="text" name="parent_first_name[]" placeholder="First name">
            </div>
            <div class="form-group">
                <label>Last Name</label>
                <input type="text" name="parent_last_name[]" placeholder="Surname">
            </div>
            <div class="form-group">
                <label>Occupation</label>
                <input type="text" name="parent_occupation[]" placeholder="e.g. Teacher">
            </div>
            <div class="form-group">
                <label>Employer</label>
                <input type="text" name="parent_employer[]" placeholder="Company / Organisation">
            </div>
            <div class="form-group">
                <label>Phone Number</label>
                <input type="tel" name="parent_phone[]" placeholder="+263 77 123 4567">
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="parent_email[]" placeholder="email@example.com">
            </div>
            <div class="form-group">
                <label>National ID</label>
                <input type="text" name="parent_national_id[]" placeholder="ID Number">
            </div>
            <div class="form-group full-width">
                <label>Address</label>
                <textarea name="parent_address[]" rows="2" placeholder="Full address"></textarea>
            </div>
        </div>
    `;

    container.appendChild(div);
}

// expose functions for inline onclick handlers
window.removeRow = removeRow;
window.addEducationRow = addEducationRow;
window.addWorkRow = addWorkRow;
window.addParentRow = addParentRow;

// ===========================================================
// Draft autosave for student forms
// ===========================================================
function setupDraftAutosave() {
    const form = document.getElementById('studentForm');
    if (!form) return;

    const studentId = form.getAttribute('data-student-id') || 'new';
    const draftKey = `tit_student_draft_${studentId}`;
    let isDirty = false;
    let saveTimer = null;

    const fields = form.querySelectorAll('input, select, textarea');

    function serialize() {
        const data = {};
        fields.forEach(field => {
            if (!field.name || field.type === 'file' || field.type === 'password') return;

            if (field.type === 'checkbox' || field.type === 'radio') {
                if (!Array.isArray(data[field.name])) data[field.name] = [];
                if (field.checked) data[field.name].push(field.value);
            } else {
                data[field.name] = field.value;
            }
        });
        return data;
    }

    function restore(data) {
        if (!data || typeof data !== 'object') return;
        fields.forEach(field => {
            if (!field.name || !(field.name in data)) return;

            if (field.type === 'checkbox' || field.type === 'radio') {
                const values = Array.isArray(data[field.name]) ? data[field.name] : [data[field.name]];
                field.checked = values.includes(field.value);
            } else {
                field.value = data[field.name] ?? '';
            }
        });
    }

    try {
        const raw = localStorage.getItem(draftKey);
        if (raw) restore(JSON.parse(raw));
    } catch (error) {
        console.warn('Draft restore failed', error);
    }

    form.addEventListener('input', () => {
        isDirty = true;
        if (saveTimer) clearTimeout(saveTimer);

        saveTimer = setTimeout(() => {
            try {
                localStorage.setItem(draftKey, JSON.stringify(serialize()));
            } catch (error) {
                console.warn('Draft save failed', error);
            }
        }, 300);
    });

    form.addEventListener('submit', () => {
        isDirty = false;
        try {
            localStorage.removeItem(draftKey);
        } catch (error) {
            console.warn('Draft clear failed', error);
        }
    });

    window.addEventListener('beforeunload', (event) => {
        if (!isDirty) return;
        event.preventDefault();
        event.returnValue = '';
    });
}
