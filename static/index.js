function refreshTable() {
    fetch('/api/history')
        .then(response => response.json())
        .then(data => {
            const logContent = document.getElementById("log-content");

            if (data.length === 0) {
                logContent.innerHTML = '目前沒有記錄。';
                return;
            }

            let htmlContent = "";
            [...data].reverse().forEach((row, index) => {
                const isLatest = index === 0 ? '<span class="badge bg-success ms-1">最新紀錄</span>' : '';
                htmlContent += `
                        <p style="line-height: 1.5; border-bottom: 1px dashed rgba(8, 24, 94, 0.2); padding-bottom: 8px;">
                            ${row.dt} ${isLatest}
                        </p>
                    `;
            });

            logContent.innerHTML = htmlContent;
        })
        .catch(error => console.error('Error fetching data:', error));
}

setInterval(refreshTable, 5000);

window.onload = refreshTable;
