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
let currentAudio = null;
let lastAlertMessage = "";
let nextAudioTimeout = null;
let loopAudioTimer = null;
let blockedAudio = "";
let hasShownSuccessAlert = false;

function getAudioSrcByMessage(msg) {
    if (!msg) return "";

    if (msg.includes("[A]}")) {
        if (msg.includes("請服用") && msg.includes("時段的藥")) {
            if (msg.includes("早餐")) return "/static/audio/02.mp3";
            if (msg.includes("午餐")) return "/static/audio/03.mp3";
            if (msg.includes("晚餐")) return "/static/audio/04.mp3";
        }

        if (msg.includes("已服用完") && msg.includes("時段的藥")) {
            if (msg.includes("早餐")) return "/static/audio/05.mp3";
            if (msg.includes("午餐")) return "/static/audio/06.mp3";
            if (msg.includes("晚餐")) return "/static/audio/07.mp3";
        }
    }

    if (msg.includes("還沒到服用藥的時段，請放下藥盒")) {
        return "/static/audio/01.mp3";
    }

    if (msg.includes("請服用") && msg.includes("時段的藥")) {
        if (msg.includes("早餐")) return "/static/audio/02.mp3";
        if (msg.includes("午餐")) return "/static/audio/03.mp3";
        if (msg.includes("晚餐")) return "/static/audio/04.mp3";
    }

    if (msg.includes("已服用完") && msg.includes("時段的藥")) {
        if (msg.includes("早餐")) return "/static/audio/05.mp3";
        if (msg.includes("午餐")) return "/static/audio/06.mp3";
        if (msg.includes("晚餐")) return "/static/audio/07.mp3";
    }

    if (msg.includes("準備服用") && msg.includes("時段的藥")) {
        if (msg.includes("早餐")) return "/static/audio/08.mp3";
        if (msg.includes("午餐")) return "/static/audio/09.mp3";
        if (msg.includes("晚餐")) return "/static/audio/10.mp3";
    }

    return "";
}

function playStatusAudio(audioSrc) {
    if (!audioSrc) return;

    if (loopAudioTimer) {
        clearInterval(loopAudioTimer);
    }

    const startNewAudio = () => {
        currentAudio = new Audio(audioSrc);
        currentAudio.play()
            .then(() => {
                console.log("語音播放成功！");
                blockedAudio = "";
            })
            .catch(err => {
                console.log("瀏覽器阻擋自動播放，需要使用者點擊網頁任意地方：", err);

                blockedAudio = audioSrc;
            });

        loopAudioTimer = setInterval(() => {
            if (currentAudio) {
                currentAudio.currentTime = 0;
                currentAudio.play().catch(e => console.log(e));
            }
        }, 300000);
    };

    if (currentAudio && !currentAudio.paused) {
        currentAudio.onended = function () {
            nextAudioTimeout = setTimeout(() => {
                startNewAudio();
            }, 1000);
        };
    } else {
        if (nextAudioTimeout) clearTimeout(nextAudioTimeout);
        startNewAudio();
    }
}

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

            const web_alertMsg = document.getElementById('alert-msg');
            if (data.alert_message) {
                web_alertMsg.innerText = data.alert_message.replace('[A]', '');
                web_alertMsg.classList.remove('alert-urgent', 'alert-done');

                if (data.alert_message.includes('請服用') || data.alert_message.includes('還沒到')) {
                    web_alertMsg.classList.add('alert-urgent');
                }
                else if (data.alert_message.includes('已服用完')) {
                    web_alertMsg.classList.add('alert-done');
                }

                if (data.alert_message !== lastAlertMessage) {
                    console.log(`狀態改變！從 [${lastAlertMessage}] 變成 [${data.alert_message}]`);

                    const audioSrc = getAudioSrcByMessage(data.alert_message);

                    playStatusAudio(audioSrc);

                    lastAlertMessage = data.alert_message;
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
            const web_alertMsg = document.getElementById('alert-msg');
            web_alertMsg.innerText = "系統連線中斷...";
            web_alertMsg.classList.remove('alert-urgent', 'alert-done');
            web_alertMsg.classList.add('alert-broken');
        });
}
setInterval(fetchSystemStatus, 1000);

window.onload = function () {
    updateClock();
    fetchSystemStatus();

    alert("【系統提示】語音提醒功能已被瀏覽器暫停。\n請點擊「確定」後，\n待網頁載入結束後，點擊網頁任意一處，\n以啟用服藥語音通知！");

    document.body.addEventListener('click', () => {
        console.log("使用者互動偵測成功，音效功能已就緒。");
        if (blockedAudio) {
            playStatusAudio(blockedAudio);
        } else {
            if (!hasShownSuccessAlert) {
                alert("【系統提示】語音提醒功能已啟用！\n未來每當有服藥提醒時，您都會聽到語音通知。");
                hasShownSuccessAlert = true;
            }
        }
    }, { once: true });
};