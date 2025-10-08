(function(){
  const Global = window.Global || (window.Global = {});
  Global.base = Global.base || 'http://localhost:8000';

  function ensureNotifyRoot(){
    let root = document.getElementById('notify-root');
    if(!root){
      root = document.createElement('div');
      root.id = 'notify-root';
      root.style.position = 'fixed';
      root.style.top = '16px';
      root.style.right = '16px';
      root.style.zIndex = '9999';
      document.body.appendChild(root);
    }
    return root;
  }

  function notify(message, type){
    const root = ensureNotifyRoot();
    const item = document.createElement('div');
    item.className = 'notify-item ' + (type || 'info');
    item.textContent = message;
    root.appendChild(item);
    setTimeout(()=>{ item.classList.add('show'); }, 10);
    setTimeout(()=>{
      item.classList.remove('show');
      setTimeout(()=>{ item.remove(); }, 250);
    }, 3000);
  }

  async function fetchJson(path, options){
    const url = (path.startsWith('http') ? path : (Global.base + path));
    const headers = Object.assign({ 'Accept': 'application/json' }, (options && options.headers) || {});
    try{
      const sid = (typeof localStorage!=='undefined' && localStorage.getItem('session_id')) || (typeof sessionStorage!=='undefined' && sessionStorage.getItem('session_id')) || undefined;
      if(sid && !headers['X-Session-Id']) headers['X-Session-Id'] = sid;
    }catch(_){ }
    const resp = await fetch(url, Object.assign({ headers }, Object.assign({}, options || {}, { headers })));
    const ct = resp.headers.get('content-type') || '';
    if(ct.includes('application/json')){
      const data = await resp.json();
      if(!resp.ok){ throw new Error(data && (data.message || data.error) || resp.statusText); }
      return data;
    }
    const text = await resp.text();
    if(!resp.ok){ throw new Error(text || resp.statusText); }
    return text;
  }

  function notifyError(err, fallback){
    const msg = (err && (err.message || err.toString && err.toString())) || fallback || '发生错误';
    notify(msg, 'error');
  }

  // 简易头部导航
  function initLayout(options){
    const active = (options && options.active) || '';
    if(document.getElementById('global-navbar')) return;
    const bar = document.createElement('div');
    bar.id = 'global-navbar';
    bar.innerHTML = (
      '<div style="position:sticky;top:0;z-index:50;background:#0f172a;color:#fff">' +
      '  <div style="max-width:1024px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;justify-content:space-between">' +
      '    <div style="font-weight:700">Netdisk 控制台</div>' +
      '    <nav style="display:flex;gap:12px;font-size:14px">' +
      `      <a href="/login" style="color:${active==='login'?'#93c5fd':'#fff'};text-decoration:${active==='login'?'underline':'none'}">登录</a>` +
      `      <a href="/admin" style="color:${active==='admin'?'#93c5fd':'#fff'};text-decoration:${active==='admin'?'underline':'none'}">管理</a>` +
      `      <a href="/user" style="color:${active==='user'?'#93c5fd':'#fff'};text-decoration:${active==='user'?'underline':'none'}">用户</a>` +
      '    </nav>' +
      '  </div>' +
      '</div>'
    );
    document.body.prepend(bar);
  }

  // MCP 后端常用 API 封装
  const api = {
    _cid(){ try{ return (typeof localStorage!=='undefined' && localStorage.getItem('netdisk_client_id')) || undefined; }catch(_){ return undefined; } },
    _withCidParams(params){ const cid = api._cid(); return Object.assign({}, params||{}, cid?{ client_id: cid }:{}); },
    _withCidBody(data){ const cid = api._cid(); return Object.assign({}, data||{}, cid?{ client_id: cid }:{}); },
    status: () => fetchJson('/oauth/status'),
    reset: () => fetchJson('/oauth/reset', { method: 'POST' }),
    userInfo: () => fetchJson('/user/info'),
    authResult: () => fetchJson('/auth/result'),
    // 简单节流/退避器：避免频控（31034）
    _limiter: (function(){
      const state = { lastTime: {}, minIntervalMs: { listall: 8000, metas: 8000, catinfo: 8000 } };
      function now(){ return Date.now(); }
      async function wait(ms){ return new Promise(r=>setTimeout(r, ms)); }
      function nextDelay(key){ const base = key==='listall'?8000:8000; const jitter = Math.floor(Math.random()*400)+200; return base + jitter; }
      async function gate(key){
        const t = now();
        const last = state.lastTime[key] || 0;
        const gap = (state.minIntervalMs[key]||0) - (t - last);
        if(gap>0){ await wait(gap); }
        state.lastTime[key] = now();
      }
      async function withBackoff(key, fn){
        let attempt = 0; let delay = nextDelay(key);
        while(true){
          await gate(key);
          const res = await fn();
          if(res && res.status === 'error'){
            const msg = (res.message||'').toLowerCase();
            const hitFreq = msg.includes('31034') || msg.includes('hit frequency limit');
            if(hitFreq && attempt < 3){ attempt++; await wait(delay); delay = Math.min(60000, delay*2); continue; }
          }
          return res;
        }
      }
      return { withBackoff };
    })(),
    listFiles: (params)=> fetchJson(`/api/files?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    listDirs: (params)=> fetchJson(`/api/dirs?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    search: (params)=> fetchJson(`/api/search?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    copy: (data)=> fetchJson('/api/copy', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    move: (data)=> fetchJson('/api/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    remove: (data)=> fetchJson('/api/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    rename: (data)=> fetchJson('/api/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    download: (data)=> fetchJson('/api/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    downloads: (data)=> fetchJson('/api/downloads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    downloadUrl: (params)=> fetchJson(`/api/download_url?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    downloadProbe: (params)=> {
      try{
        const usp = new URLSearchParams(api._withCidParams(params||{}));
        if(params && params.path){ usp.set('path', params.path); }
        if(params && params.url){ usp.set('url', params.url); }
        usp.set('redirect','1');
        const url = `${Global.base}/api/download?${usp.toString()}`;
        try{ window.open(url, '_blank'); }
        catch(_){ location.href = url; }
        return Promise.resolve({ status: 'success', message: 'redirected' });
      }catch(err){
        notifyError(err, '下载启动失败');
        return Promise.resolve({ status: 'error', message: err && err.message || '下载启动失败' });
      }
    },
    // 任务队列
    taskEnqueue: (data)=> fetchJson('/api/tasks/enqueue', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody(data)) }),
    taskEnqueueBatch: (data)=> fetchJson('/api/tasks/enqueue_batch', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody(data)) }),
    taskList: (client_id)=> fetchJson(`/api/tasks?${new URLSearchParams(api._withCidParams(client_id?{client_id}:{})).toString()}`),
    taskDetail: (id, client_id)=> fetchJson(`/api/tasks/${encodeURIComponent(id)}?${new URLSearchParams(api._withCidParams(client_id?{client_id}:{})).toString()}`),
    taskControl: (action, client_id)=> fetchJson('/api/tasks/control', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody({ action, client_id })) }),
    upload: (data)=> fetchJson('/api/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(api._withCidBody(data)) }),
    mediaList: (params)=> api._limiter.withBackoff('listall', async ()=>{
      return await fetchJson(`/api/multimedia/list?${new URLSearchParams(api._withCidParams(params)).toString()}`);
    }),
    mediaMetas: (data)=> api._limiter.withBackoff('metas', async ()=>{
      return await fetchJson('/api/multimedia/metas', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody(data)) });
    }),
    categoryInfo: (params)=> api._limiter.withBackoff('catinfo', async ()=>{
      return await fetchJson(`/api/categoryinfo?${new URLSearchParams(api._withCidParams(params)).toString()}`);
    }),
    shareCreate: (data)=> fetchJson('/api/share/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody(data)) }),
    shareInfo: (params)=> fetchJson(`/api/share/info?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    shareTransfer: (data)=> fetchJson('/api/share/transfer', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(api._withCidBody(data)) }),
    shareDlink: (params)=> fetchJson(`/api/share/dlink?${new URLSearchParams(api._withCidParams(params)).toString()}`),
    // global notifications
    notifyPublish: (data)=> {
      try{
        const CLIENT_ID_KEY = 'netdisk_client_id';
        const cid = (typeof localStorage!=='undefined' && localStorage.getItem(CLIENT_ID_KEY)) || undefined;
        const sender_sid = (typeof sessionStorage!=='undefined' && (sessionStorage.getItem('sender_sid') || (function(){ const v = Math.random().toString(36).slice(2)+Date.now().toString(36); try{ sessionStorage.setItem('sender_sid', v); }catch(_){} return v; })())) || undefined;
        const payload = Object.assign({}, data||{}, cid?{ client_id: cid }:{}, sender_sid?{ sender_sid }:{});
        return fetchJson('/api/notify', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      }catch(_){ return fetchJson('/api/notify', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data||{}) }); }
    },
    notifyPoll: (params, opts)=> fetchJson(`/api/notify?${new URLSearchParams(params||{}).toString()}`, opts||{}),
  };

  // 多类别顺序请求辅助（避免逗号聚合触发频控）。
  // 调用者传入 categories 数组和一个生成参数的函数（或固定参数），逐个类别串行调用 mediaList。
  Global.mediaFetchByCategories = async function(categories, baseParams){
    const results = [];
    for(const cat of (categories||[])){
      const params = Object.assign({}, (typeof baseParams==='function'? baseParams(cat) : (baseParams||{})), { category: cat });
      const res = await api.mediaList(params);
      results.push({ category: cat, result: res });
    }
    return results;
  };

  Global.notify = notify;
  Global.notifyError = notifyError;
  Global.fetchJson = fetchJson;
  Global.initLayout = initLayout;
  Global.api = api;

  // cross-page notification poller (soft real-time)
  (function startNotifyPoller(){
    try{
      const usp = new URLSearchParams((location && location.search) || '');
      if(usp.get('nopoll')==='1' || usp.get('disable_notify_poller')==='1') return;
    }catch(_){ }
    if(window.Global && Global.disableNotifyPoller){ return; }
    let since = 0;
    const CLIENT_ID_KEY = 'netdisk_client_id';
    const selfCid = (typeof localStorage!=='undefined' && localStorage.getItem(CLIENT_ID_KEY)) || null;
    const selfSid = (typeof sessionStorage!=='undefined' && (sessionStorage.getItem('sender_sid') || (function(){ const v = Math.random().toString(36).slice(2)+Date.now().toString(36); try{ sessionStorage.setItem('sender_sid', v); }catch(_){} return v; })())) || null;
    async function tick(){
      try{
        // add a small timeout to avoid hanging
        const ctrl = (typeof AbortController!=='undefined') ? new AbortController() : null;
        const timer = ctrl ? setTimeout(()=>{ try{ ctrl.abort(); }catch(_){} }, 2500) : null;
        const res = await api.notifyPoll({ since, limit: 50 }, ctrl ? { signal: ctrl.signal } : undefined);
        if(timer) clearTimeout(timer);
        const items = (res && res.items) || [];
        if(items.length){
          items.forEach(it=>{ try{ if(!selfSid || it.sender_sid !== selfSid){ const prefix = it.sender_role ? `[${it.sender_role}] ` : ''; const txt = prefix + (it.id?`[${it.id}] `:'') + (it.text||''); notify(txt, it.type||'info'); } }catch(_){} });
          since = res.now || (items[items.length-1].ts || since);
        } else if(res && res.now){
          since = res.now;
        }
      }catch(_){ /* ignore transient errors */ }
      setTimeout(tick, 1500);
    }
    tick();
  })();

  // 通知管理功能
  Global.NotificationManager = {
    async fetchNotifications(userId, { status = 'unread', page = 1, size = 20, type, channel } = {}) {
      try {
        const params = new URLSearchParams({ user_id: userId, status, page: String(page), size: String(size) });
        if (type) params.set('type', type);
        if (channel) params.set('channel', channel);
        const response = await fetchJson(`/api/notifications?${params.toString()}`);
        return response; // {status, items, page, size, has_more, next_page} 或旧结构
      } catch (error) {
        console.error('获取通知失败:', error);
        return { status: 'error', message: error.message };
      }
    },

    async markNotificationRead(userId, notificationId) {
      try {
        const params = new URLSearchParams({ user_id: userId });
        const response = await fetchJson(`/api/notifications/${notificationId}/read?${params.toString()}`, { method: 'POST' });
        return response;
      } catch (error) {
        console.error('标记通知已读失败:', error);
        return { status: 'error', message: error.message };
      }
    },

    async reportEvent(notificationId, userId, event, extra) {
      try {
        const params = new URLSearchParams({ user_id: userId });
        const body = { event, extra };
        return await fetchJson(`/api/notifications/${notificationId}/events?${params.toString()}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      } catch (error) {
        console.error('上报通知事件失败:', error);
        return { status: 'error', message: error.message };
      }
    },

    async getUnreadCount(userId) {
      try {
        const params = new URLSearchParams({ user_id: userId });
        const response = await fetchJson(`/api/notifications/unread-count?${params.toString()}`);
        return response.status === 'success' ? (response.unread_count ?? response.count ?? 0) : 0;
      } catch (error) {
        console.error('获取未读数量失败:', error);
        return 0;
      }
    },

    async markAllRead(userId) {
      try {
        const params = new URLSearchParams({ user_id: userId });
        const response = await fetchJson(`/api/notifications/read-all?${params.toString()}`, { method: 'POST' });
        return response;
      } catch (error) {
        console.error('标记所有通知已读失败:', error);
        return { status: 'error', message: error.message };
      }
    }
  };

  // 用户会话管理
  Global.SessionManager = {
    async getCurrentSession() {
      try {
        const response = await fetchJson('/oauth/session/latest');
        return response;
      } catch (error) {
        console.error('获取会话信息失败:', error);
        return { status: 'error', message: error.message };
      }
    },

    getStoredUserInfo() {
      try {
        const userInfo = localStorage.getItem('user_info');
        return userInfo ? JSON.parse(userInfo) : null;
      } catch (error) {
        console.error('获取存储的用户信息失败:', error);
        return null;
      }
    },

    storeUserInfo(userInfo) {
      try {
        localStorage.setItem('user_info', JSON.stringify(userInfo));
      } catch (error) {
        console.error('存储用户信息失败:', error);
      }
    },

    async getUserId() {
      // 先从localStorage获取
      const storedInfo = this.getStoredUserInfo();
      if (storedInfo && storedInfo.user_id) {
        return storedInfo.user_id;
      }

      // 如果localStorage没有，从服务器获取
      try {
        const session = await this.getCurrentSession();
        if (session.status === 'success' && session.user_id) {
          // 存储到localStorage
          this.storeUserInfo(session);
          return session.user_id;
        }
      } catch (error) {
        console.error('获取用户ID失败:', error);
      }

      return null;
    }
  };

  // 通知轮询管理
  Global.NotificationPoller = {
    pollInterval: null,
    pollIntervalMs: 60000, // 60秒

    startPolling(onUpdate) {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
      }

      // 立即执行一次
      this.pollNotifications(onUpdate);

      // 设置定时器
      this.pollInterval = setInterval(() => {
        this.pollNotifications(onUpdate);
      }, this.pollIntervalMs);
    },

    stopPolling() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }
    },

    async pollNotifications(onUpdate) {
      try {
        const userId = await Global.SessionManager.getUserId();
        if (!userId) {
          return;
        }

        const unreadCount = await Global.NotificationManager.getUnreadCount(userId);
        if (typeof onUpdate === 'function') {
          onUpdate(unreadCount);
        }
      } catch (error) {
        console.error('轮询通知失败:', error);
      }
    }
  };

  // 导出函数供其他脚本使用
  Global.fetchNotifications = (userId, options) => Global.NotificationManager.fetchNotifications(userId, options||{});
  Global.markNotificationRead = (userId, id) => Global.NotificationManager.markNotificationRead(userId, id);
  Global.getUnreadCount = (userId) => Global.NotificationManager.getUnreadCount(userId);
  Global.getUserId = () => Global.SessionManager.getUserId();

})();


