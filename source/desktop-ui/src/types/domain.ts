export type LanguageCode = "vi" | "ko" | "en" | "ja" | "zh";

export type ThemeMode = "light" | "dark";

export type ApprovalStatus = "pending" | "approved" | "rejected";

export type UserRole = "personal" | "shared_read" | "shared_create" | "master";

export type Profile = {
  can_manage_company?: boolean;
  department?: string|null;
  job_title?: string|null;
  avatar_path?: string|null;
  company_id?: string | null;
  company_role?: "COMPANY_MASTER" | "MEMBER" | null;
  id: string;
  email: string;
  display_name: string | null;
  nationality: string | null;
  approval_status: ApprovalStatus;
  role: UserRole;
  login_started_at: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  approved_by: string | null;
};

export type TranslationRow = {
  key: string;
  ko: string;
  vi: string;
  en: string;
  ja: string;
  zh: string;
  "zh-TW"?: string;
  created_at?: string;
  updated_at?: string;
};

export type AdminStats = {
  total: number;
  pending: number;
  approved: number;
  personal: number;
  shared_read: number;
  shared_create: number;
  master: number;
};
