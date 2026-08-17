document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    fetchRules();
    fetchRecentJobs();

    // Auto refresh stats every 3 seconds
    setInterval(() => {
        fetchStats();
        fetchRecentJobs();
    }, 3000);

    document.getElementById('btn-refresh').addEventListener('click', () => {
        fetchStats();
        fetchRules();
        fetchRecentJobs();
    });

    document.getElementById('create-rule-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const keywordInput = document.getElementById('keyword');
        const msgInput = document.getElementById('dm-message');

        const payload = {
            keyword: keywordInput.value.trim(),
            dm_message: msgInput.value.trim()
        };

        try {
            const response = await fetch('/rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                keywordInput.value = '';
                msgInput.value = '';
                fetchRules();
                fetchStats();
            } else {
                const err = await response.json();
                alert(`Error creating rule: ${err.detail || 'Unknown error'}`);
            }
        } catch (error) {
            alert(`Failed to create rule: ${error.message}`);
        }
    });

    document.getElementById('simulate-webhook-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const textInput = document.getElementById('simulate-text');
        const userInput = document.getElementById('simulate-user');

        const timestampStr = new Date().toISOString();
        const commentId = `cmt_sim_${Date.now()}`;
        const eventId = `evt_sim_${Date.now()}`;

        const payload = {
            event_id: eventId,
            event_type: "comment.created",
            sent_at: timestampStr,
            data: {
                comment_id: commentId,
                post_id: "post_simulated_123",
                text: textInput.value.trim(),
                created_at: timestampStr,
                from: {
                    user_id: `usr_${userInput.value.trim().toLowerCase()}`,
                    username: userInput.value.trim()
                }
            }
        };

        try {
            const response = await fetch('/webhook', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                textInput.value = '';
                fetchStats();
                fetchRecentJobs();
                const btn = document.getElementById('btn-simulate-webhook');
                const origText = btn.innerHTML;
                btn.innerHTML = '<span>Sent! Refreshing...</span>';
                btn.style.opacity = '0.7';
                setTimeout(() => {
                    btn.innerHTML = origText;
                    btn.style.opacity = '1';
                }, 1500);
            } else {
                const err = await response.json();
                alert(`Error sending webhook: ${err.detail || 'Unknown error'}`);
            }
        } catch (error) {
            alert(`Failed to send webhook: ${error.message}`);
        }
    });
});

async function fetchStats() {
    try {
        const res = await fetch('/stats');
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('stat-sent').textContent = data.sent;
        document.getElementById('stat-queued').textContent = data.queued;
        document.getElementById('stat-blocked').textContent = data.duplicates_blocked;
        document.getElementById('stat-failed').textContent = data.failed;
    } catch (err) {
        console.error('Failed to fetch stats:', err);
    }
}

async function fetchRules() {
    try {
        const res = await fetch('/rules');
        if (!res.ok) return;
        const rules = await res.json();

        const countBadge = document.getElementById('rule-count');
        countBadge.textContent = `${rules.length} Rule${rules.length === 1 ? '' : 's'}`;

        const container = document.getElementById('rules-list');
        if (rules.length === 0) {
            container.innerHTML = '<div class="empty-state">No rules created yet.</div>';
            return;
        }

        container.innerHTML = rules.map(r => `
            <div class="rule-item">
                <span class="rule-keyword">${escapeHtml(r.keyword)}</span>
                <span class="rule-msg">${escapeHtml(r.dm_message)}</span>
            </div>
        `).join('');
    } catch (err) {
        console.error('Failed to fetch rules:', err);
    }
}

async function fetchRecentJobs() {
    try {
        const res = await fetch('/api/jobs');
        if (!res.ok) return;
        const jobs = await res.json();

        const container = document.getElementById('jobs-list');
        if (jobs.length === 0) {
            container.innerHTML = '<tr><td colspan="5" class="empty-state">No recent activity found</td></tr>';
            return;
        }

        container.innerHTML = jobs.map(j => `
            <tr>
                <td><strong>${escapeHtml(j.user_id)}</strong></td>
                <td><code>${escapeHtml(j.comment_id)}</code></td>
                <td><span class="status-pill status-${j.status}">${j.status}</span></td>
                <td>${j.attempts}</td>
                <td><code>${j.dm_id ? escapeHtml(j.dm_id) : '-'}</code></td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Failed to fetch jobs:', err);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
