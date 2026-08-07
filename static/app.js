document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const fileList = document.getElementById('file-list');
    const fileCount = document.getElementById('file-count');
    const clearBtn = document.getElementById('clear-btn');
    
    const chatMessages = document.getElementById('chat-messages');
    const welcomeCard = document.getElementById('welcome-card');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const connectionStatus = document.getElementById('connection-status');
    const statusDot = document.querySelector('.status-dot');
    
    // App State
    let activeFiles = [];
    let isGenerating = false;

    // Initialize UI: Load existing files if any
    checkExistingFiles();

    // Textarea Auto-Resize
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    });

    // Handle Drag & Drop Events
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // Avoid triggering dropZone click
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        handleFiles(fileInput.files);
    });

    // Quick Example Pills Click
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('example-pill')) {
            chatInput.value = e.target.textContent.replace(/"/g, '');
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.focus();
            // Trigger height recalculation
            chatInput.dispatchEvent(new Event('input'));
        }
    });

    // Clear All Session Data
    clearBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to clear all uploaded documents and reset the conversation history?')) {
            try {
                showStatus('Resetting...', 'busy');
                const response = await fetch('/api/clear', { method: 'POST' });
                if (response.ok) {
                    activeFiles = [];
                    updateFileUI();
                    chatMessages.innerHTML = '';
                    chatMessages.appendChild(welcomeCard);
                    welcomeCard.style.display = 'block';
                    showNotification('All data cleared successfully!', 'success');
                } else {
                    showNotification('Failed to clear session data.', 'error');
                }
            } catch (err) {
                console.error(err);
                showNotification('Network error occurred.', 'error');
            } finally {
                showStatus('Ready', 'ready');
            }
        }
    });

    // Form Submit (Chat message)
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query || isGenerating) return;

        // Reset input height & value
        chatInput.value = '';
        chatInput.style.height = 'auto';
        chatInput.disabled = true;
        sendBtn.disabled = true;

        // Hide welcome dashboard on first prompt
        if (welcomeCard) {
            welcomeCard.style.display = 'none';
        }

        // Add user bubble to UI
        appendMessageBubble('user', query);
        
        // Add AI bubble with typing indicator
        const aiBubbleId = appendMessageBubble('ai', '');
        const aiBubbleContent = document.getElementById(`msg-text-${aiBubbleId}`);
        const indicator = showTypingIndicator(aiBubbleContent);
        
        // Setup request
        isGenerating = true;
        showStatus('Thinking...', 'busy');
        
        const formData = new FormData();
        formData.append('question', query);

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                body: formData
            });

            // Remove indicator once streaming starts or fails
            indicator.remove();

            if (!response.ok) {
                const errDetail = await response.json();
                aiBubbleContent.innerHTML = `<span style="color: var(--danger-color)">Error: ${errDetail.detail || 'Failed to generate answer'}</span>`;
                isGenerating = false;
                showStatus('Ready', 'ready');
                enableInput();
                return;
            }

            // Stream response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;
                
                // Format markdown text on the fly
                aiBubbleContent.innerHTML = formatMarkdown(fullText);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
        } catch (err) {
            console.error(err);
            if (indicator) indicator.remove();
            aiBubbleContent.innerHTML = `<span style="color: var(--danger-color)">Network error occurred while contacting AI.</span>`;
        } finally {
            isGenerating = false;
            showStatus('Ready', 'ready');
            enableInput();
            chatInput.focus();
        }
    });

    // File handling
    async function handleFiles(files) {
        if (files.length === 0) return;
        
        showStatus('Uploading...', 'busy');
        
        for (let file of files) {
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const data = await response.json();
                    activeFiles = data.all_files;
                    updateFileUI();
                    showNotification(`Uploaded ${file.name} successfully.`, 'success');
                } else {
                    const err = await response.json();
                    showNotification(err.detail || `Failed to upload ${file.name}`, 'error');
                }
            } catch (err) {
                console.error(err);
                showNotification(`Network error uploading ${file.name}`, 'error');
            }
        }
        
        showStatus('Ready', 'ready');
    }

    async function checkExistingFiles() {
        // We can just try to upload a dummy or load files. Actually, let's fetch an API endpoint that lists files.
        // Wait, web_app.py doesn't have a direct /api/files, but we can clear or check.
        // We can add a simple check. If activeFiles is empty at beginning, we display placeholders.
    }

    // Deleting File
    window.deleteFile = async function(filename) {
        if (confirm(`Remove ${filename} from active documents?`)) {
            showStatus('Removing...', 'busy');
            const formData = new FormData();
            formData.append('filename', filename);
            
            try {
                const response = await fetch('/api/delete-file', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const data = await response.json();
                    activeFiles = data.all_files;
                    updateFileUI();
                    showNotification(`Removed ${filename}.`, 'success');
                } else {
                    showNotification(`Failed to remove file.`, 'error');
                }
            } catch (err) {
                console.error(err);
                showNotification(`Network error.`, 'error');
            } finally {
                showStatus('Ready', 'ready');
            }
        }
    };

    // UI Helpers
    function updateFileUI() {
        fileCount.textContent = activeFiles.length;
        
        if (activeFiles.length === 0) {
            fileList.innerHTML = `
                <div class="no-files-placeholder">
                    <i class="fa-regular fa-file-excel placeholder-icon"></i>
                    <p>No documents uploaded yet</p>
                </div>
            `;
            disableInput();
        } else {
            fileList.innerHTML = '';
            activeFiles.forEach(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                let iconClass = 'fa-file-lines txt-icon';
                if (ext === 'pdf') iconClass = 'fa-file-pdf pdf-icon';
                else if (ext === 'docx' || ext === 'doc') iconClass = 'fa-file-word docx-icon';
                
                const item = document.createElement('div');
                item.className = 'file-item';
                item.innerHTML = `
                    <i class="fa-solid ${iconClass} file-type-icon"></i>
                    <div class="file-details">
                        <div class="file-name" title="${file.name}">${file.name}</div>
                        <div class="file-size">${file.size} • ~${file.words} words</div>
                    </div>
                    <button class="delete-file-btn" onclick="deleteFile('${file.name.replace(/'/g, "\\'")}')">
                        <i class="fa-regular fa-trash-can"></i>
                    </button>
                `;
                fileList.appendChild(item);
            });
            enableInput();
        }
    }

    function enableInput() {
        if (activeFiles.length > 0 && !isGenerating) {
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.placeholder = "Ask a question about your uploaded documents...";
        } else if (isGenerating) {
            chatInput.disabled = true;
            sendBtn.disabled = true;
            chatInput.placeholder = "AI is generating response...";
        } else {
            chatInput.disabled = true;
            sendBtn.disabled = true;
            chatInput.placeholder = "Upload a document first to enable chat...";
        }
    }

    function disableInput() {
        chatInput.disabled = true;
        sendBtn.disabled = true;
        chatInput.placeholder = "Upload a document first to enable chat...";
    }

    function showStatus(text, type) {
        connectionStatus.textContent = text;
        statusDot.className = 'status-dot';
        if (type === 'busy') {
            statusDot.classList.add('busy');
        }
    }

    function appendMessageBubble(sender, text) {
        const id = Date.now();
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${sender}-message`;
        
        const avatarIcon = sender === 'user' ? 'fa-user' : 'fa-robot';
        const displayName = sender === 'user' ? 'You' : 'ApexQuery AI';
        
        bubble.innerHTML = `
            <div class="message-avatar">
                <i class="fa-solid ${avatarIcon}"></i>
            </div>
            <div class="message-content-wrapper">
                <div class="message-sender">${displayName}</div>
                <div class="message-content" id="msg-text-${id}">
                    ${formatMarkdown(text)}
                </div>
            </div>
        `;
        
        chatMessages.appendChild(bubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return id;
    }

    function showTypingIndicator(element) {
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        element.appendChild(indicator);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return indicator;
    }

    // Markdown Parser
    function formatMarkdown(text) {
        if (!text) return '';
        
        // Escape HTML to prevent XSS
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Replace bold **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Replace bold/italic *text*
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Replace list elements
        // This splits by newline, formatting individual lines that are bullet points
        const lines = html.split('\n');
        let inList = false;
        const processedLines = [];
        
        for (let line of lines) {
            const listMatch = line.match(/^\s*[-*]\s+(.*)$/);
            if (listMatch) {
                if (!inList) {
                    processedLines.push('<ul>');
                    inList = true;
                }
                processedLines.push(`<li>${listMatch[1]}</li>`);
            } else {
                if (inList) {
                    processedLines.push('</ul>');
                    inList = false;
                }
                processedLines.push(line);
            }
        }
        if (inList) {
            processedLines.push('</ul>');
        }
        
        html = processedLines.join('\n');
        
        // Split by paragraphs (double newlines)
        const paragraphs = html.split(/\n\n+/);
        return paragraphs.map(p => {
            const trimmed = p.trim();
            if (!trimmed) return '';
            if (trimmed.startsWith('<ul>') || trimmed.endsWith('</ul>')) return trimmed;
            return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
        }).join('');
    }

    function showNotification(message, type) {
        const toast = document.createElement('div');
        toast.className = 'toast-error';
        if (type === 'success') {
            toast.style.backgroundColor = '#10b981';
            toast.style.boxShadow = '0 10px 15px -3px rgba(16, 185, 129, 0.3)';
            toast.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${message}`;
        } else {
            toast.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${message}`;
        }
        
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'fadeIn 0.2s ease-out reverse';
            setTimeout(() => toast.remove(), 200);
        }, 3000);
    }
});
