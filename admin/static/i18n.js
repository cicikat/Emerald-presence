(function () {
  'use strict';

  const DEFAULT_LANGUAGE = 'zh-CN';
  const STORAGE_KEY = 'presence.admin.language';
  const SUPPORTED_LANGUAGES = new Set(['zh-CN', 'en']);

  const I18N = {
    'zh-CN': {
      'app.title': 'His Presence 管理面板',
      'auth.title': '🤖 管理面板',
      'auth.subtitle': 'His Presence · 输入管理密钥登录',
      'auth.login': '登录',
      'common.language': '语言',
      'nav.console': '运维控制台',
      'nav.setup': '配置',
      'nav.group.creation': '🎨 创作',
      'nav.character': '角色卡',
      'nav.lorebook': '现实设定',
      'nav.dream_settings': '梦境设定',
      'nav.group.operations': '🛠 运维',
      'nav.status': '系统状态',
      'nav.scheduler': '调度器',
      'nav.users': '用户管理',
      'nav.logs': '错误日志',
      'nav.auth_tokens': 'Token',
      'nav.model_routing': '模型路由',
      'nav.relationship_facts': '关系事实',
      'nav.group.internal_state': '🔬 内部状态',
      'nav.mood': '情绪·花园',
      'nav.dream_state': '梦境状态',
      'nav.memory': '记忆探查',
      'nav.hidden_state': '隐性状态',
      'nav.chat_log': '聊天日志',
      'nav.runtime': '运行时内部态',
      'nav.group.observation': '🔍 观测',
      'nav.growth': '成长',
      'nav.visual': '视觉',
      'nav.spend': '支出',
      'nav.group_arbiter': '群聊仲裁',
      'nav.memory_summary': '记忆摘要',
      'nav.prompt_layers': 'Prompt 层检视',
      'nav.probe': '探针观测',
      'nav.dream_prompt': '梦境 Prompt',
      'nav.trigger_catalog': '触发器目录',
      'nav.vector_store': '向量库',
      'nav.provenance': '印象溯源',
      'nav.pet': '宠物',
      'nav.chat_with': '与',
    },
    en: {
      'app.title': 'His Presence Admin Panel',
      'auth.title': '🤖 Admin Panel',
      'auth.subtitle': 'His Presence · Enter the admin key to sign in',
      'auth.login': 'Sign in',
      'common.language': 'Language',
      'nav.console': 'Operations Console',
      'nav.setup': 'Setup',
      'nav.group.creation': '🎨 Creation',
      'nav.character': 'Characters',
      'nav.lorebook': 'Reality Lore',
      'nav.dream_settings': 'Dream Settings',
      'nav.group.operations': '🛠 Operations',
      'nav.status': 'System Status',
      'nav.scheduler': 'Scheduler',
      'nav.users': 'Users',
      'nav.logs': 'Error Logs',
      'nav.auth_tokens': 'Tokens',
      'nav.model_routing': 'Model Routing',
      'nav.relationship_facts': 'Relationship Facts',
      'nav.group.internal_state': '🔬 Internal State',
      'nav.mood': 'Mood & Garden',
      'nav.dream_state': 'Dream State',
      'nav.memory': 'Memory Explorer',
      'nav.hidden_state': 'Hidden State',
      'nav.chat_log': 'Chat Logs',
      'nav.runtime': 'Runtime Internals',
      'nav.group.observation': '🔍 Observation',
      'nav.growth': 'Growth',
      'nav.visual': 'Vision',
      'nav.spend': 'Spending',
      'nav.group_arbiter': 'Group Arbiter',
      'nav.memory_summary': 'Memory Summary',
      'nav.prompt_layers': 'Prompt Layers',
      'nav.probe': 'Probe Inspector',
      'nav.dream_prompt': 'Dream Prompt',
      'nav.trigger_catalog': 'Trigger Catalog',
      'nav.vector_store': 'Vector Store',
      'nav.provenance': 'Impression Provenance',
      'nav.pet': 'Pet',
      'nav.chat_with': 'Chat with',
    },
  };

  function readLanguage() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return SUPPORTED_LANGUAGES.has(saved) ? saved : DEFAULT_LANGUAGE;
    } catch (_error) {
      return DEFAULT_LANGUAGE;
    }
  }

  let currentLanguage = readLanguage();

  function format(template, params) {
    if (!params) return template;
    return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, name) =>
      Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : `{${name}}`
    );
  }

  function t(key, fallback, params) {
    const active = I18N[currentLanguage] || {};
    if (Object.prototype.hasOwnProperty.call(active, key)) return format(active[key], params);
    console.debug(`[admin-i18n] missing ${currentLanguage}: ${key}`);
    const chinese = I18N[DEFAULT_LANGUAGE] || {};
    const value = Object.prototype.hasOwnProperty.call(chinese, key) ? chinese[key] : fallback;
    return format(value == null ? key : value, params);
  }

  function applyI18n(root) {
    const scope = root || document;
    document.documentElement.lang = currentLanguage;
    document.title = t('app.title', document.title);
    scope.querySelectorAll('[data-i18n]').forEach(element => {
      const key = element.dataset.i18n;
      const fallback = element.dataset.i18nFallback || element.textContent;
      element.textContent = t(key, fallback);
    });
    scope.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
      const key = element.dataset.i18nPlaceholder;
      element.placeholder = t(key, element.placeholder);
    });
    const selector = document.getElementById('admin-language-select');
    if (selector) selector.value = currentLanguage;
  }

  function setLanguage(language) {
    if (!SUPPORTED_LANGUAGES.has(language) || language === currentLanguage) return;
    currentLanguage = language;
    try { localStorage.setItem(STORAGE_KEY, language); } catch (_error) { /* best effort */ }
    applyI18n();
    window.dispatchEvent(new CustomEvent('admin-language-changed', {detail: {language}}));
  }

  function getLanguage() {
    return currentLanguage;
  }

  window.AdminI18n = {I18N, applyI18n, getLanguage, setLanguage, t};
  window.t = t;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => applyI18n(), {once: true});
  } else {
    applyI18n();
  }
})();
