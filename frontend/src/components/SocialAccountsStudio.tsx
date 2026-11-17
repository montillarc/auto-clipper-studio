import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  FolderPlus,
  KeyRound,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
  XCircle,
} from 'lucide-react';
import type {
  AccountCategoryKey,
  SocialAccountEntry,
  SocialHubApiSettings,
  SocialHubConfigResponse,
  SocialPlatformKey,
  SocialPlatformVerifyResponse,
} from '../types';
import { type ActiveOperation, getHubCategoryOptions } from './studioHelpers';

export interface SocialAccountsStudioProps {
  hubConfig: SocialHubConfigResponse;
  verifyResults: Partial<Record<SocialPlatformKey, SocialPlatformVerifyResponse>>;
  activeOp: ActiveOperation;
  verifyingPlatform: SocialPlatformKey | null;
  pendingYouTubeAuthUrl?: string | null;
  onChangeHubConfig: (next: SocialHubConfigResponse) => void;
  onSaveHubConfig: () => void;
  onVerifyPlatform: (platform: SocialPlatformKey) => void;
  onAuthorizeYouTube?: () => void;
  onCancelYouTubeOAuth?: () => void;
  onCreateCategory?: (payload: {
    label: string;
    description: string;
    topic_keywords: string[];
  }) => Promise<string | null> | void;
  onDeleteCategory?: (catKey: string) => void;
}

const PLATFORM_LABELS: Record<SocialPlatformKey, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  tiktok: 'TikTok',
  facebook: 'Facebook',
};

const API_CARDS_META: Array<{
  platform: SocialPlatformKey;
  title: string;
  subtitle: string;
}> = [
  {
    platform: 'youtube',
    title: 'YouTube Data API v3',
    subtitle: 'OAuth 2.0 y subida automática de Shorts por categoría.',
  },
  {
    platform: 'instagram',
    title: 'Instagram Graph API',
    subtitle: 'Meta Business ID y publicación de Reels sin límite de puntaje.',
  },
  {
    platform: 'tiktok',
    title: 'TikTok Content Posting API',
    subtitle: 'Modo Direct Post o Borrador por perfil de TikTok.',
  },
  {
    platform: 'facebook',
    title: 'Facebook Reels Graph API',
    subtitle: 'Page Access Token y distribución directa en Pages.',
  },
];

export function SocialAccountsStudio({
  hubConfig,
  verifyResults,
  activeOp,
  verifyingPlatform,
  pendingYouTubeAuthUrl,
  onChangeHubConfig,
  onSaveHubConfig,
  onVerifyPlatform,
  onAuthorizeYouTube,
  onCancelYouTubeOAuth,
  onCreateCategory,
  onDeleteCategory,
}: SocialAccountsStudioProps) {
  const categoryOptions = getHubCategoryOptions(hubConfig);
  const [selectedCategory, setSelectedCategory] = useState<AccountCategoryKey>('principales');
  const [keywordsDrafts, setKeywordsDrafts] = useState<Partial<Record<AccountCategoryKey, string>>>({});
  const [newCatLabel, setNewCatLabel] = useState<string>('');
  const [newCatKeywords, setNewCatKeywords] = useState<string>('');
  const isSaving = activeOp === 'save_social_hub';
  const isCreatingCategory = activeOp === 'create_social_category';
  const isDeletingCategory = activeOp === 'delete_social_category';

  useEffect(() => {
    if (!hubConfig.categories[selectedCategory]) {
      setSelectedCategory(categoryOptions[0]?.key || 'principales');
    }
  }, [hubConfig.categories, selectedCategory, categoryOptions]);

  const currentCat = hubConfig.categories[selectedCategory];
  const keywordsValue =
    keywordsDrafts[selectedCategory] ?? (currentCat?.topic_keywords || []).join(', ');

  const handleSubmitNewCategory = async () => {
    const cleanLabel = newCatLabel.trim();
    if (!cleanLabel || !onCreateCategory) return;
    const kws = newCatKeywords
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const createdKey = await onCreateCategory({
      label: cleanLabel,
      description: `Categoría personalizada para ${cleanLabel}.`,
      topic_keywords: kws,
    });
    if (createdKey) {
      setSelectedCategory(createdKey);
      setNewCatLabel('');
      setNewCatKeywords('');
    }
  };

  const handleKeywordsChange = (catKey: AccountCategoryKey, rawText: string) => {
    setKeywordsDrafts((prev) => ({ ...prev, [catKey]: rawText }));
    const parsed = rawText
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    onChangeHubConfig({
      ...hubConfig,
      categories: {
        ...hubConfig.categories,
        [catKey]: {
          ...hubConfig.categories[catKey],
          topic_keywords: parsed,
        },
      },
    });
  };

  const handleUpdateAccount = (
    catKey: AccountCategoryKey,
    accountId: string,
    patch: Partial<SocialAccountEntry>
  ) => {
    const prevAccounts = hubConfig.categories[catKey].accounts || [];
    onChangeHubConfig({
      ...hubConfig,
      categories: {
        ...hubConfig.categories,
        [catKey]: {
          ...hubConfig.categories[catKey],
          accounts: prevAccounts.map((acc) => (acc.id === accountId ? { ...acc, ...patch } : acc)),
        },
      },
    });
  };

  const handleAddAccount = (catKey: AccountCategoryKey) => {
    const newId = `acct_${catKey}_${Date.now()}`;
    const newEntry: SocialAccountEntry = {
      id: newId,
      platform: 'instagram',
      handle: '@nueva_cuenta',
      display_name: 'Nueva Cuenta',
      external_id: '',
      enabled: true,
    };
    const prevAccounts = hubConfig.categories[catKey].accounts || [];
    onChangeHubConfig({
      ...hubConfig,
      categories: {
        ...hubConfig.categories,
        [catKey]: {
          ...hubConfig.categories[catKey],
          accounts: [...prevAccounts, newEntry],
        },
      },
    });
  };

  const handleRemoveAccount = (catKey: AccountCategoryKey, accountId: string) => {
    const prevAccounts = hubConfig.categories[catKey].accounts || [];
    onChangeHubConfig({
      ...hubConfig,
      categories: {
        ...hubConfig.categories,
        [catKey]: {
          ...hubConfig.categories[catKey],
          accounts: prevAccounts.filter((acc) => acc.id !== accountId),
        },
      },
    });
  };

  const updateApiField = <P extends keyof SocialHubApiSettings>(
    platform: P,
    field: keyof SocialHubApiSettings[P],
    value: string
  ) => {
    onChangeHubConfig({
      ...hubConfig,
      api_settings: {
        ...hubConfig.api_settings,
        [platform]: {
          ...hubConfig.api_settings[platform],
          [field]: value,
        },
      },
    });
  };

  const renderApiFields = (platform: SocialPlatformKey) => {
    const api = hubConfig.api_settings;
    if (platform === 'youtube') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="api-yt-client-id"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                OAuth Client ID
              </label>
              <input
                id="api-yt-client-id"
                type="text"
                value={api.youtube.client_id}
                onChange={(e) => updateApiField('youtube', 'client_id', e.target.value)}
                placeholder="123456-xxx.apps.googleusercontent.com"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="api-yt-client-secret"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                OAuth Client Secret
              </label>
              <input
                id="api-yt-client-secret"
                type="password"
                value={api.youtube.client_secret}
                onChange={(e) => updateApiField('youtube', 'client_secret', e.target.value)}
                placeholder="•••• (dejar igual o pegar nuevo)"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="api-yt-cat-id"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Categoría YouTube ID
              </label>
              <input
                id="api-yt-cat-id"
                type="text"
                value={api.youtube.default_category_id}
                onChange={(e) => updateApiField('youtube', 'default_category_id', e.target.value)}
                placeholder="22 (Gente y blogs) / 20 (Gaming)"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
              />
            </div>
            <div>
              <label
                htmlFor="api-yt-json"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                client_secret.json (Opcional)
              </label>
              <input
                id="api-yt-json"
                type="text"
                value={api.youtube.client_secret_json || ''}
                onChange={(e) => updateApiField('youtube', 'client_secret_json', e.target.value)}
                placeholder='{"installed":{...}}'
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </div>
      );
    }

    if (platform === 'instagram') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="api-ig-app-id"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Meta App ID
              </label>
              <input
                id="api-ig-app-id"
                type="text"
                value={api.instagram.app_id}
                onChange={(e) => updateApiField('instagram', 'app_id', e.target.value)}
                placeholder="App ID de Meta Developers"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
              />
            </div>
            <div>
              <label
                htmlFor="api-ig-app-secret"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Meta App Secret
              </label>
              <input
                id="api-ig-app-secret"
                type="password"
                value={api.instagram.app_secret}
                onChange={(e) => updateApiField('instagram', 'app_secret', e.target.value)}
                placeholder="•••• (App Secret)"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label
                htmlFor="api-ig-token"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Long-Lived Access Token
              </label>
              <input
                id="api-ig-token"
                type="password"
                value={api.instagram.access_token}
                onChange={(e) => updateApiField('instagram', 'access_token', e.target.value)}
                placeholder="EAAG..."
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="api-ig-business-id"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Business ID
              </label>
              <input
                id="api-ig-business-id"
                type="text"
                value={api.instagram.business_id}
                onChange={(e) => updateApiField('instagram', 'business_id', e.target.value)}
                placeholder="Ej. 123456789012345"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
              />
            </div>
          </div>
        </div>
      );
    }

    if (platform === 'tiktok') {
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="api-tt-client-key"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                TikTok Client Key
              </label>
              <input
                id="api-tt-client-key"
                type="text"
                value={api.tiktok.client_key}
                onChange={(e) => updateApiField('tiktok', 'client_key', e.target.value)}
                placeholder="awxxxxxx..."
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="api-tt-client-secret"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                TikTok Client Secret
              </label>
              <input
                id="api-tt-client-secret"
                type="password"
                value={api.tiktok.client_secret}
                onChange={(e) => updateApiField('tiktok', 'client_secret', e.target.value)}
                placeholder="•••• (Client Secret)"
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="api-tt-token"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                OAuth Access Token
              </label>
              <input
                id="api-tt-token"
                type="password"
                value={api.tiktok.access_token}
                onChange={(e) => updateApiField('tiktok', 'access_token', e.target.value)}
                placeholder="act.xxxx..."
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="api-tt-mode"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Modo de Publicación
              </label>
              <select
                id="api-tt-mode"
                value={api.tiktok.publish_mode}
                onChange={(e) => updateApiField('tiktok', 'publish_mode', e.target.value)}
                className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              >
                <option value="DIRECT_POST">DIRECT_POST (API Pública)</option>
                <option value="INBOX_UPLOAD">INBOX_UPLOAD (Borrador App Móvil)</option>
                <option value="TIKTOK_STUDIO">TIKTOK_STUDIO (TikTok Studio Web — PC con permiso)</option>
              </select>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label
              htmlFor="api-fb-app-id"
              className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
            >
              Facebook App ID
            </label>
            <input
              id="api-fb-app-id"
              type="text"
              value={api.facebook.app_id}
              onChange={(e) => updateApiField('facebook', 'app_id', e.target.value)}
              placeholder="Meta App ID"
              className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
            />
          </div>
          <div className="sm:col-span-2">
            <label
              htmlFor="api-fb-page-token"
              className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
            >
              Page Access Token
            </label>
            <input
              id="api-fb-page-token"
              type="password"
              value={api.facebook.page_access_token}
              onChange={(e) => updateApiField('facebook', 'page_access_token', e.target.value)}
              placeholder="EAAG... (Token permanente de Página)"
              className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
            />
          </div>
        </div>
        <div>
          <label
            htmlFor="api-fb-graph-ver"
            className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
          >
            Versión Graph API
          </label>
          <input
            id="api-fb-graph-ver"
            type="text"
            value={api.facebook.graph_version}
            onChange={(e) => updateApiField('facebook', 'graph_version', e.target.value)}
            placeholder="v21.0"
            className="w-full h-10 px-3 rounded-xl bg-zinc-50 dark:bg-zinc-950/70 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
          />
        </div>
      </div>
    );
  };

  return (
    <section
      aria-label="Configuración de Cuentas Sociales y APIs"
      className="space-y-6 animate-fadeIn"
    >
      {/* Cabecera del Hub + Guardar */}
      <div className="rounded-3xl border border-zinc-200 dark:border-white/10 bg-white/90 dark:bg-[#11151F]/90 backdrop-blur-xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 text-xs font-semibold text-blue-600 dark:text-blue-400">
            <Users className="w-4 h-4 shrink-0" />
            <span>Distribución Multi-Categoría y Credenciales Oficiales</span>
          </div>
          <h2 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-white">
            Hub de Cuentas &amp; APIs de Subida
          </h2>
          <p className="text-xs text-zinc-600 dark:text-zinc-400">
            Todos los Shorts generados se publican sin restricción de puntaje hacia las redes activas de sus categorías asignadas.
          </p>
        </div>

        <button
          type="button"
          onClick={onSaveHubConfig}
          disabled={isSaving}
          className="h-10 px-5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold inline-flex items-center justify-center gap-2 whitespace-nowrap leading-none shadow-sm transition-colors disabled:opacity-50 shrink-0"
        >
          <Save className="w-4 h-4 shrink-0" />
          {isSaving ? 'Guardando Hub...' : 'Guardar Configuración de Cuentas y APIs'}
        </button>
      </div>

      {/* Sección 1: Cuentas por Categoría */}
      <div className="rounded-3xl border border-zinc-200 dark:border-white/10 bg-white/90 dark:bg-[#11151F]/90 backdrop-blur-xl p-6 shadow-sm space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight text-zinc-900 dark:text-white">
              Cuentas por Categoría Editorial
            </h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              Configura las cuentas destino y palabras clave temáticas para auto-clasificar los Shorts.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {categoryOptions.map((catMeta) => {
              const cat = hubConfig.categories[catMeta.key];
              const isSelected = selectedCategory === catMeta.key;
              const activeCount = (cat?.accounts || []).filter((a) => a.enabled).length;
              return (
                <button
                  key={catMeta.key}
                  type="button"
                  onClick={() => setSelectedCategory(catMeta.key)}
                  className={`h-10 px-4 rounded-xl text-xs font-semibold inline-flex items-center justify-center gap-2 whitespace-nowrap leading-none transition-all border ${
                    isSelected
                      ? 'bg-zinc-900 text-white border-zinc-900 dark:bg-white dark:text-zinc-900 dark:border-white shadow-sm'
                      : 'bg-zinc-100 text-zinc-700 border-zinc-200 hover:bg-zinc-200 dark:bg-zinc-800/70 dark:text-zinc-200 dark:border-zinc-700 dark:hover:bg-zinc-800'
                  }`}
                >
                  <span>{cat?.label || catMeta.label}</span>
                  <span className="px-1.5 py-0.5 rounded-md bg-black/15 dark:bg-black/25 text-[10px] tabular-nums">
                    {activeCount}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Barra para crear nuevas categorías de cuentas personalizadas */}
        {onCreateCategory && (
          <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.08] bg-zinc-50/70 dark:bg-[#090B10]/60 p-4 grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
            <div className="md:col-span-4">
              <label
                htmlFor="new-account-category-label"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Nombre de nueva categoría
              </label>
              <input
                id="new-account-category-label"
                aria-label="Nombre de nueva categoría"
                type="text"
                value={newCatLabel}
                onChange={(e) => setNewCatLabel(e.target.value)}
                placeholder="Ej. Cuentas Podcast, IRL, Clips"
                className="w-full h-10 px-3 rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>

            <div className="md:col-span-5">
              <label
                htmlFor="new-account-category-keywords"
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1"
              >
                Palabras clave de tema (opcional, separadas por coma)
              </label>
              <input
                id="new-account-category-keywords"
                aria-label="Palabras clave de nueva categoría"
                type="text"
                value={newCatKeywords}
                onChange={(e) => setNewCatKeywords(e.target.value)}
                placeholder="tertulia, invitado, irl, calle"
                className="w-full h-10 px-3 rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>

            <div className="md:col-span-3">
              <button
                type="button"
                onClick={() => void handleSubmitNewCategory()}
                disabled={isCreatingCategory || !newCatLabel.trim()}
                className="w-full h-10 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none transition-colors disabled:opacity-50"
              >
                <FolderPlus className="w-3.5 h-3.5 shrink-0" />
                {isCreatingCategory ? 'Creando...' : 'Crear Categoría'}
              </button>
            </div>
          </div>
        )}

        {currentCat && (
          <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-zinc-950/40 p-5 space-y-4">
            <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
              <div className="space-y-1 max-w-xl">
                <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
                  {currentCat.label}
                </h4>
                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                  {currentCat.description}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {currentCat.is_custom && onDeleteCategory && (
                  <button
                    type="button"
                    disabled={isDeletingCategory}
                    onClick={() => onDeleteCategory(selectedCategory)}
                    className="h-10 px-4 rounded-xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-700 dark:text-red-300 text-xs font-medium inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-3.5 h-3.5 shrink-0" />
                    Eliminar Categoría
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleAddAccount(selectedCategory)}
                  className="h-10 px-4 rounded-xl bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-white text-xs font-medium inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none transition-colors shrink-0"
                >
                  <Plus className="w-3.5 h-3.5 shrink-0" />
                  Agregar Cuenta
                </button>
              </div>
            </div>

            <div>
              <label
                htmlFor={`topic-keywords-${selectedCategory}`}
                className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400 mb-1.5 flex items-center gap-1.5"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                Palabras clave de auto-categorización por tema (separadas por coma)
              </label>
              <input
                id={`topic-keywords-${selectedCategory}`}
                type="text"
                value={keywordsValue}
                onChange={(e) => handleKeywordsChange(selectedCategory, e.target.value)}
                placeholder="gameplay, rtx, ps5, zelda..."
                className="w-full h-10 px-3 rounded-xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-2.5">
              {(currentCat.accounts || []).map((acc) => (
                <div
                  key={acc.id}
                  className="grid grid-cols-1 md:grid-cols-12 gap-2.5 items-center p-3 rounded-xl bg-white dark:bg-zinc-900/90 border border-zinc-200 dark:border-zinc-800"
                >
                  <div className="md:col-span-2">
                    <select
                      aria-label={`Plataforma de ${acc.handle}`}
                      value={acc.platform}
                      onChange={(e) =>
                        handleUpdateAccount(selectedCategory, acc.id, {
                          platform: e.target.value as SocialPlatformKey,
                        })
                      }
                      className="w-full h-10 px-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-xs font-medium text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
                    >
                      {(['instagram', 'youtube', 'tiktok', 'facebook'] as SocialPlatformKey[]).map(
                        (plat) => (
                          <option key={plat} value={plat}>
                            {PLATFORM_LABELS[plat]}
                          </option>
                        )
                      )}
                    </select>
                  </div>

                  <div className="md:col-span-3">
                    <input
                      aria-label={`Usuario o Handle de ${acc.display_name || acc.id}`}
                      type="text"
                      value={acc.handle}
                      onChange={(e) =>
                        handleUpdateAccount(selectedCategory, acc.id, { handle: e.target.value })
                      }
                      placeholder="@cuenta"
                      className="w-full h-10 px-3 rounded-lg bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
                    />
                  </div>

                  <div className="md:col-span-3">
                    <input
                      aria-label={`Nombre visible de ${acc.handle}`}
                      type="text"
                      value={acc.display_name}
                      onChange={(e) =>
                        handleUpdateAccount(selectedCategory, acc.id, {
                          display_name: e.target.value,
                        })
                      }
                      placeholder="Nombre descriptivo"
                      className="w-full h-10 px-3 rounded-lg bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500"
                    />
                  </div>

                  <div className="md:col-span-2">
                    <input
                      aria-label={`ID externo de ${acc.handle}`}
                      type="text"
                      value={acc.external_id}
                      onChange={(e) =>
                        handleUpdateAccount(selectedCategory, acc.id, {
                          external_id: e.target.value,
                        })
                      }
                      placeholder="IG / Page / Channel ID"
                      className="w-full h-10 px-3 rounded-lg bg-zinc-50 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-900 dark:text-zinc-100 outline-none focus:border-blue-500 tabular-nums"
                    />
                  </div>

                  <div className="md:col-span-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        handleUpdateAccount(selectedCategory, acc.id, { enabled: !acc.enabled })
                      }
                      className={`flex-1 h-10 px-3 rounded-lg text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none border transition-colors ${
                        acc.enabled
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/35'
                          : 'bg-zinc-100 text-zinc-500 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700'
                      }`}
                    >
                      {acc.enabled ? 'Activa' : 'Pausada'}
                    </button>
                    <button
                      type="button"
                      aria-label={`Eliminar cuenta ${acc.handle}`}
                      onClick={() => handleRemoveAccount(selectedCategory, acc.id)}
                      className="h-10 w-10 rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/60 text-red-600 dark:text-red-400 inline-flex items-center justify-center shrink-0 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Sección 2: APIs y Automatización */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-blue-500 shrink-0" />
          <h3 className="text-base font-semibold tracking-tight text-zinc-900 dark:text-white">
            Credenciales de APIs y Automatización
          </h3>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {API_CARDS_META.map((card) => {
            const vRes = verifyResults[card.platform];
            const isVerifying =
              activeOp === 'verify_social_platform' && verifyingPlatform === card.platform;

            return (
              <div
                key={card.platform}
                className="rounded-2xl border border-zinc-200 dark:border-white/10 bg-white/90 dark:bg-[#11151F]/90 p-5 shadow-sm flex flex-col justify-between gap-4"
              >
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
                        {card.title}
                      </h4>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                        {card.subtitle}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      {card.platform === 'youtube' && onAuthorizeYouTube && (
                        <button
                          type="button"
                          onClick={onAuthorizeYouTube}
                          disabled={activeOp === 'authorize_youtube_oauth'}
                          className="h-10 px-3.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none shrink-0 transition-colors disabled:opacity-50"
                        >
                          <KeyRound className={`w-3.5 h-3.5 ${activeOp === 'authorize_youtube_oauth' ? 'animate-spin' : ''}`} />
                          Autorizar OAuth
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onVerifyPlatform(card.platform)}
                        disabled={isVerifying}
                        className="h-10 px-3.5 rounded-xl bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 border border-zinc-200 dark:border-zinc-700 text-xs font-medium text-zinc-900 dark:text-zinc-100 inline-flex items-center justify-center gap-1.5 whitespace-nowrap leading-none shrink-0 transition-colors disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isVerifying ? 'animate-spin' : ''}`} />
                        Probar Conexión
                      </button>
                    </div>
                  </div>

                  {renderApiFields(card.platform)}

                  {card.platform === 'youtube' && pendingYouTubeAuthUrl && (
                    <div className="rounded-xl px-3 py-2.5 text-xs border bg-cyan-50/90 dark:bg-cyan-950/40 border-cyan-200 dark:border-cyan-500/35 text-cyan-900 dark:text-cyan-100 flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">
                        Autorización de Google abierta en otra pestaña.
                      </span>
                      <div className="flex flex-wrap items-center gap-2 shrink-0">
                        <a
                          href={pendingYouTubeAuthUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="h-10 px-3 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors"
                        >
                          Abrir Google OAuth ↗
                        </a>
                        {onCancelYouTubeOAuth && (
                          <button
                            type="button"
                            onClick={onCancelYouTubeOAuth}
                            className="h-10 px-3 rounded-lg border border-zinc-300 dark:border-white/15 bg-white/80 dark:bg-zinc-900/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 text-xs font-medium inline-flex items-center justify-center whitespace-nowrap leading-none transition-colors"
                          >
                            Cancelar
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {vRes && (
                  <div
                    className={`rounded-xl px-3 py-2.5 text-xs border flex items-start gap-2 ${
                      vRes.connected
                        ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/70 text-emerald-800 dark:text-emerald-200'
                        : 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800/70 text-amber-800 dark:text-amber-200'
                    }`}
                  >
                    {vRes.connected ? (
                      <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-500" />
                    ) : (
                      <XCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
                    )}
                    <div className="min-w-0">
                      <div className="font-semibold">{vRes.status_label}</div>
                      <div className="text-[11px] opacity-90 break-words">{vRes.detail}</div>
                    </div>
                  </div>
                )}

                {!vRes && (
                  <div className="text-[11px] text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
                    <span>Los tokens guardados se devuelven enmascarados (••••) y nunca se pierden al actualizar otras opciones.</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
