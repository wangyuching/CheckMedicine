// 網頁即時時鐘
function updateClock() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const hh = String(now.getHours()).padStart(2, '0');
    const min = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('live-clock').innerText = `${yyyy}-${mm}-${dd} ${hh}:${min}:${ss}`;
}
setInterval(updateClock, 1000);

let lastDataString = "";

function fetchSystemStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const currentDataString = JSON.stringify(data);
            if (currentDataString === lastDataString) {
                return;
            }
            lastDataString = currentDataString;
            console.log("資料已更新，進行 UI 更新", data);

            const alertMsg = document.getElementById('alert-msg');
            if (data.alert_message) {
                alertMsg.innerText = data.alert_message;
                alertMsg.classList.remove('alert-urgent', 'alert-done');

                if (data.alert_message.includes('請服用') || data.alert_message.includes('還沒到')) {
                    alertMsg.classList.add('alert-urgent');
                }
                else if (data.alert_message.includes('已服用完')) {
                    alertMsg.classList.add('alert-done');
                }
            }

            const meals = ['breakfast', 'lunch', 'dinner'];
            const currentHour = new Date().getHours();

            meals.forEach(meal => {
                const itemCard = document.getElementById(`meal-${meal}`);
                const iconSpan = document.getElementById(`icon-${meal}`);
                const tagSpan = document.getElementById(`tag-${meal}`);
                const timeSpan = document.getElementById(`time-${meal}`);

                itemCard.classList.remove('current-active');

                if (meal === 'breakfast' && currentHour === 7) itemCard.classList.add('current-active');
                if (meal === 'lunch' && currentHour === 12) itemCard.classList.add('current-active');
                if (meal === 'dinner' && currentHour === 17) itemCard.classList.add('current-active');

                if (data[meal].status === 'Checked') {
                    iconSpan.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10B981;"></i>';
                    tagSpan.className = 'status-tag tag-checked';
                    tagSpan.innerText = '已服藥';
                    timeSpan.innerText = `服藥時間：${data[meal].time}`;
                } else if (data[meal].status === 'Missed') {
                    iconSpan.innerHTML = '<i class="fa-solid fa-circle-xmark" style="color:#EF4444;"></i>';
                    tagSpan.className = 'status-tag tag-missed';
                    tagSpan.innerText = '未服藥';
                    timeSpan.innerText = '未在指定時間內服藥';
                } else {
                    iconSpan.innerHTML = '<i class="fa-solid fa-circle-minus" style="color:#9CA3AF;"></i>';
                    tagSpan.className = 'status-tag tag-pending';
                    tagSpan.innerText = '準備中';
                    timeSpan.innerText = '服藥時間：--:--:--';
                }
            });
        })
        .catch(err => {
            console.error("無法取得 API 狀態:", err);
            document.getElementById('alert-msg').innerText = "系統連線中斷...";
        });
}

setInterval(fetchSystemStatus, 1000);
window.onload = function () {
    updateClock();
    fetchSystemStatus();
};