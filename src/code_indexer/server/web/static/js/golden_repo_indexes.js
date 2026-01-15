/**
 * Golden Repository Index Management
 *
 * Provides UI functionality for managing indexes on golden repositories:
 * - Displaying index status (present/not present)
 * - Adding new indexes with confirmation
 * - Polling job status and displaying progress
 * - Handling success/failure feedback
 */

/**
 * Show the add index form for a repository
 * @param {string} alias - Repository alias
 */
function showAddIndexForm(alias) {
    const form = document.getElementById(`add-index-form-${alias}`);
    if (form) {
        form.style.display = 'block';
    }
}

/**
 * Hide the add index form for a repository
 * @param {string} alias - Repository alias
 */
function hideAddIndexForm(alias) {
    const form = document.getElementById(`add-index-form-${alias}`);
    if (form) {
        form.style.display = 'none';
    }
}

/**
 * Submit add index request with confirmation dialog
 * @param {string} alias - Repository alias
 */
async function submitAddIndex(alias) {
    const selectElement = document.getElementById(`index-type-${alias}`);
    if (!selectElement) {
        console.error(`Select element not found for alias: ${alias}`);
        return;
    }

    const indexType = selectElement.value;
    if (!indexType) {
        alert('Please select an index type');
        return;
    }

    // AC7: Confirmation dialog before submission
    const indexTypeLabel = selectElement.options[selectElement.selectedIndex].text;
    if (!confirm(`Add ${indexTypeLabel} index to repository "${alias}"?\n\nThis operation may take several minutes.`)) {
        return;
    }

    // Hide the form
    hideAddIndexForm(alias);

    // Show job progress container with loading indicator
    const progressContainer = document.getElementById(`job-progress-${alias}`);
    const statusText = document.getElementById(`job-status-text-${alias}`);
    const spinner = document.getElementById(`job-spinner-${alias}`);

    if (progressContainer && statusText && spinner) {
        progressContainer.style.display = 'block';
        statusText.textContent = 'submitting...';
        spinner.style.display = 'inline-block';
    }

    try {
        // Get CSRF token from page
        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value || '';

        // Submit POST request to add index
        const response = await fetch(`/api/admin/golden-repos/${alias}/indexes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'same-origin',  // Include cookies (session_id) in request
            body: JSON.stringify({ index_type: indexType })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const jobId = data.job_id;

        // Start polling job status
        if (jobId) {
            pollJobStatus(alias, jobId);
        } else {
            throw new Error('No job_id returned from server');
        }

    } catch (error) {
        console.error('Failed to submit add index request:', error);

        // AC6: Show error feedback
        if (statusText) {
            statusText.textContent = 'error';
            statusText.style.color = 'var(--pico-color-red-550)';
        }
        if (spinner) {
            spinner.style.display = 'none';
        }

        const progressDetails = document.getElementById(`job-progress-details-${alias}`);
        if (progressDetails) {
            progressDetails.innerHTML = `<p class="error-text">Failed to submit job: ${error.message}</p>`;
        }

        // Show error message and allow retry
        setTimeout(() => {
            alert(`Failed to add index: ${error.message}\n\nPlease try again or contact administrator.`);
            if (progressContainer) {
                progressContainer.style.display = 'none';
            }
        }, 500);
    }
}

/**
 * Poll job status every 5 seconds until completion
 * @param {string} alias - Repository alias
 * @param {string} jobId - Job ID to poll
 */
function pollJobStatus(alias, jobId) {
    const progressContainer = document.getElementById(`job-progress-${alias}`);
    const statusText = document.getElementById(`job-status-text-${alias}`);
    const spinner = document.getElementById(`job-spinner-${alias}`);
    const progressDetails = document.getElementById(`job-progress-details-${alias}`);

    if (!progressContainer || !statusText || !spinner || !progressDetails) {
        console.error(`Progress elements not found for alias: ${alias}`);
        return;
    }

    const pollInterval = 5000; // 5 seconds
    let pollCount = 0;
    const maxPolls = 360; // 30 minutes max (360 * 5 seconds)

    const poll = async () => {
        pollCount++;

        if (pollCount > maxPolls) {
            console.error(`Max polling attempts reached for job ${jobId}`);
            statusText.textContent = 'timeout';
            statusText.style.color = 'var(--pico-color-red-550)';
            spinner.style.display = 'none';
            progressDetails.innerHTML = '<p class="error-text">Job polling timeout. Please refresh the page.</p>';
            return;
        }

        try {
            const response = await fetch(`/api/jobs/${jobId}`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const jobStatus = await response.json();
            updateJobProgress(alias, jobStatus);

            // Continue polling if job is still running
            if (jobStatus.status === 'pending' || jobStatus.status === 'running') {
                setTimeout(poll, pollInterval);
            } else if (jobStatus.status === 'completed') {
                // AC5: Success feedback - reload page to show updated index status
                setTimeout(() => {
                    showSuccessMessage('Index added successfully!');
                    // Trigger HTMX refresh of repos list
                    const refreshBtn = document.getElementById('refresh-btn');
                    if (refreshBtn) {
                        refreshBtn.click();
                    }
                }, 1000);
            } else if (jobStatus.status === 'failed') {
                // AC6: Error feedback
                setTimeout(() => {
                    alert(`Index addition failed: ${jobStatus.result?.error || 'Unknown error'}\n\nPlease try again or contact administrator.`);
                }, 500);
            }

        } catch (error) {
            console.error('Failed to poll job status:', error);
            statusText.textContent = 'error';
            statusText.style.color = 'var(--pico-color-red-550)';
            spinner.style.display = 'none';
            progressDetails.innerHTML = `<p class="error-text">Failed to retrieve job status: ${error.message}</p>`;
        }
    };

    // Start polling immediately
    poll();
}

/**
 * Update job progress UI with current status
 * @param {string} alias - Repository alias
 * @param {object} jobStatus - Job status object from API
 */
function updateJobProgress(alias, jobStatus) {
    const statusText = document.getElementById(`job-status-text-${alias}`);
    const spinner = document.getElementById(`job-spinner-${alias}`);
    const progressDetails = document.getElementById(`job-progress-details-${alias}`);

    if (!statusText || !spinner || !progressDetails) {
        return;
    }

    // Update status text with color coding
    statusText.textContent = jobStatus.status;

    if (jobStatus.status === 'completed') {
        statusText.style.color = 'var(--pico-color-green-550)';
        spinner.style.display = 'none';
    } else if (jobStatus.status === 'failed') {
        statusText.style.color = 'var(--pico-color-red-550)';
        spinner.style.display = 'none';
    } else if (jobStatus.status === 'running') {
        statusText.style.color = 'var(--pico-color-blue-550)';
        spinner.style.display = 'inline-block';
    } else {
        // pending
        statusText.style.color = 'var(--pico-color-amber-550)';
        spinner.style.display = 'inline-block';
    }

    // Build progress details HTML
    let detailsHtml = '';

    if (jobStatus.created_at) {
        detailsHtml += `<p><strong>Created:</strong> ${new Date(jobStatus.created_at).toLocaleString()}</p>`;
    }
    if (jobStatus.started_at) {
        detailsHtml += `<p><strong>Started:</strong> ${new Date(jobStatus.started_at).toLocaleString()}</p>`;
    }
    if (jobStatus.completed_at) {
        detailsHtml += `<p><strong>Completed:</strong> ${new Date(jobStatus.completed_at).toLocaleString()}</p>`;
    }
    if (jobStatus.progress) {
        detailsHtml += `<p><strong>Progress:</strong> ${jobStatus.progress}</p>`;
    }
    if (jobStatus.result) {
        if (jobStatus.status === 'completed') {
            detailsHtml += `<p class="success-text"><strong>Result:</strong> ${JSON.stringify(jobStatus.result, null, 2)}</p>`;
        } else if (jobStatus.status === 'failed') {
            detailsHtml += `<p class="error-text"><strong>Error:</strong> ${jobStatus.result.error || JSON.stringify(jobStatus.result)}</p>`;
        }
    }

    progressDetails.innerHTML = detailsHtml;
}

/**
 * Show success message to user
 * @param {string} message - Success message to display
 */
function showSuccessMessage(message) {
    const messagesContainer = document.querySelector('.golden-repos-header');
    if (!messagesContainer) {
        return;
    }

    const successArticle = document.createElement('article');
    successArticle.className = 'message-success';
    successArticle.innerHTML = `<p>${message}</p>`;

    messagesContainer.insertAdjacentElement('afterend', successArticle);

    // Remove message after 5 seconds
    setTimeout(() => {
        successArticle.remove();
    }, 5000);
}
