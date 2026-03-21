// Wait for DOM to load
document.addEventListener('DOMContentLoaded', function() {
    // File upload drag and drop functionality
    const uploadArea = document.querySelector('.upload-area');
    if (uploadArea) {
        const fileInput = document.querySelector('#file-input');
        
        uploadArea.addEventListener('click', () => {
            fileInput.click();
        });
        
        fileInput.addEventListener('change', () => {
            updateFileList(fileInput.files);
        });
        
        // Drag and drop events
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('active');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('active');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('active');
            
            const files = e.dataTransfer.files;
            fileInput.files = files;
            updateFileList(files);
        });
        
        // Display selected files
        function updateFileList(files) {
            const fileList = document.querySelector('#file-list');
            fileList.innerHTML = '';
            
            if (files.length > 0) {
                for (let i = 0; i < files.length; i++) {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'alert alert-info mb-2';
                    fileItem.innerHTML = `
                        <i class="bi bi-file-earmark-pdf"></i> ${files[i].name} (${formatFileSize(files[i].size)})
                    `;
                    fileList.appendChild(fileItem);
                }
                document.querySelector('#submit-btn').disabled = false;
            } else {
                document.querySelector('#submit-btn').disabled = true;
            }
        }
        
        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' bytes';
            else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            else return (bytes / 1048576).toFixed(1) + ' MB';
        }
    }
    
    // Category suggestion and management for supplier edit
    const supplierNameInput = document.querySelector('#supplier_name');
    const categoryInput = document.querySelector('#category');
    const suggestCategoriesBtn = document.querySelector('#suggest-categories');
    const addCategoryBtn = document.querySelector('#add-category');
    const categoriesContainer = document.querySelector('#categories-container');
    
    if (supplierNameInput && categoryInput && suggestCategoriesBtn) {
        // Add a new category field
        if (addCategoryBtn && categoriesContainer) {
            addCategoryBtn.addEventListener('click', () => {
                const newCategoryGroup = document.createElement('div');
                newCategoryGroup.className = 'input-group mb-2 additional-category';
                newCategoryGroup.innerHTML = `
                    <input type="text" class="form-control" name="additional_categories[]" placeholder="Additional category">
                    <button class="btn btn-outline-danger remove-category" type="button">
                        <i class="bi bi-x"></i>
                    </button>
                `;
                categoriesContainer.appendChild(newCategoryGroup);
                
                // Add event listener to the remove button
                const removeBtn = newCategoryGroup.querySelector('.remove-category');
                removeBtn.addEventListener('click', () => {
                    newCategoryGroup.remove();
                });
            });
            
            // Add event listeners to existing remove buttons
            document.querySelectorAll('.remove-category').forEach(button => {
                button.addEventListener('click', () => {
                    button.closest('.additional-category').remove();
                });
            });
        }
        
        // Category suggestions
        suggestCategoriesBtn.addEventListener('click', async () => {
            const supplierName = supplierNameInput.value.trim();
            if (supplierName) {
                suggestCategoriesBtn.disabled = true;
                suggestCategoriesBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i> Loading...';
                
                try {
                    const response = await fetch(`/api/suggest_categories/${encodeURIComponent(supplierName)}`);
                    const categories = await response.json();
                    
                    if (categories && categories.length > 0) {
                        showCategorySuggestions(categories);
                    } else {
                        alert('No category suggestions found for this supplier name.');
                    }
                } catch (error) {
                    console.error('Error fetching category suggestions:', error);
                    alert('Failed to get category suggestions. Please try again.');
                } finally {
                    suggestCategoriesBtn.disabled = false;
                    suggestCategoriesBtn.innerHTML = '<i class="bi bi-magic me-1"></i> Suggest';
                }
            } else {
                alert('Please enter a supplier name first.');
            }
        });
        
        function showCategorySuggestions(categories) {
            const suggestionContainer = document.querySelector('#category-suggestions');
            suggestionContainer.innerHTML = '<p class="mb-2">Suggested categories:</p>';
            
            const list = document.createElement('div');
            list.className = 'list-group mb-3';
            
            categories.forEach(category => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                
                // Create main text element
                const text = document.createElement('span');
                text.textContent = category;
                item.appendChild(text);
                
                // Create actions container
                const actions = document.createElement('div');
                actions.className = 'btn-group btn-group-sm';
                
                // Add as primary button
                const primaryBtn = document.createElement('button');
                primaryBtn.type = 'button';
                primaryBtn.className = 'btn btn-outline-primary btn-sm';
                primaryBtn.innerHTML = 'Set as Primary';
                primaryBtn.addEventListener('click', (e) => {
                    e.stopPropagation(); // Prevent triggering the parent item click
                    categoryInput.value = category;
                    suggestionContainer.innerHTML = '';
                });
                actions.appendChild(primaryBtn);
                
                // Add as additional button
                const addBtn = document.createElement('button');
                addBtn.type = 'button';
                addBtn.className = 'btn btn-outline-success btn-sm';
                addBtn.innerHTML = 'Add as Additional';
                addBtn.addEventListener('click', (e) => {
                    e.stopPropagation(); // Prevent triggering the parent item click
                    
                    // Create new category input
                    const newCategoryGroup = document.createElement('div');
                    newCategoryGroup.className = 'input-group mb-2 additional-category';
                    newCategoryGroup.innerHTML = `
                        <input type="text" class="form-control" name="additional_categories[]" value="${category}" placeholder="Additional category">
                        <button class="btn btn-outline-danger remove-category" type="button">
                            <i class="bi bi-x"></i>
                        </button>
                    `;
                    categoriesContainer.appendChild(newCategoryGroup);
                    
                    // Add event listener to the remove button
                    const removeBtn = newCategoryGroup.querySelector('.remove-category');
                    removeBtn.addEventListener('click', () => {
                        newCategoryGroup.remove();
                    });
                    
                    suggestionContainer.innerHTML = '';
                });
                actions.appendChild(addBtn);
                
                item.appendChild(actions);
                list.appendChild(item);
            });
            
            suggestionContainer.appendChild(list);
        }
    }
    
    // Initialize tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (tooltips.length > 0) {
        tooltips.forEach(tooltip => {
            new bootstrap.Tooltip(tooltip);
        });
    }
    
    // Initialize popovers
    const popovers = document.querySelectorAll('[data-bs-toggle="popover"]');
    if (popovers.length > 0) {
        popovers.forEach(popover => {
            new bootstrap.Popover(popover);
        });
    }
    
    // Alert auto-dismiss
    const alerts = document.querySelectorAll('.alert-dismissible');
    if (alerts.length > 0) {
        alerts.forEach(alert => {
            setTimeout(() => {
                const closeBtn = alert.querySelector('.btn-close');
                if (closeBtn) {
                    closeBtn.click();
                }
            }, 5000);
        });
    }
});