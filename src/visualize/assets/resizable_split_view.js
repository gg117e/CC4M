
// Event delegation for resizable split view
document.addEventListener('DOMContentLoaded', function() {
    // We use a broader event listener because the split view is created dynamically
    let isDragging = false;
    let currentContainer = null;
    let leftPane = null;
    let rightPane = null;

    document.addEventListener('mousedown', function(e) {
        if (e.target.classList.contains('split-gutter')) {
            isDragging = true;
            currentContainer = e.target.closest('.split-container');
            if (currentContainer) {
                // Find immediate children panes
                // Assuming structure: Pane1, Gutter, Pane2
                const siblings = Array.from(currentContainer.children);
                const gutterIndex = siblings.indexOf(e.target);
                leftPane = siblings[gutterIndex - 1];
                rightPane = siblings[gutterIndex + 1];
                
                document.body.style.cursor = 'col-resize';
                e.preventDefault(); // Prevent text selection
            } else {
                isDragging = false;
            }
        }
    });

    document.addEventListener('mousemove', function(e) {
        if (!isDragging || !currentContainer || !leftPane) return;

        const containerRect = currentContainer.getBoundingClientRect();
        // Calculate new width percentage for the left pane
        // Valid range: 10% to 90%
        let newLeftWidth = e.clientX - containerRect.left;
        let percentage = (newLeftWidth / containerRect.width) * 100;
        
        // Constraints
        if (percentage < 10) percentage = 10;
        if (percentage > 90) percentage = 90;

        // Apply styles
        // We use flex-basis for smooth resizing
        leftPane.style.flex = `0 0 ${percentage}%`;
        // rightPane takes remaining space naturally via flex: 1
    });

    document.addEventListener('mouseup', function(e) {
        if (isDragging) {
            isDragging = false;
            document.body.style.cursor = '';
            currentContainer = null;
            leftPane = null;
            rightPane = null;
        }
    });
});
