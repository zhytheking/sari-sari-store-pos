document.addEventListener('DOMContentLoaded', function () {
    // Fade the page in once the DOM is ready
    document.body.style.opacity = '1';

    // Auto-dismiss any .alert elements after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        setTimeout(function () {
            alerts.forEach(function (alert) {
                alert.style.transition = 'opacity 0.5s ease';
                alert.style.opacity = '0';
                setTimeout(function () {
                    if (alert.parentNode) alert.remove();
                }, 500);
            });
        }, 5000);
    }
});
