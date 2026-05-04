export interface BillingPlan {
  id: string;
  name: string;
  description: string | null;
  price_cents: number;
  input_token_quota: number;
  output_token_quota: number;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
}

export interface UserQuota {
  id: string;
  user_id: string;
  plan_id: string | null;
  input_quota_total: number;
  input_quota_used: number;
  input_quota_remaining: number;
  output_quota_total: number;
  output_quota_used: number;
  output_quota_remaining: number;
  status: string;
  first_activated_at: string;
  last_recharged_at: string | null;
}

export interface BillingOrder {
  id: string;
  order_no: string;
  user_id: string;
  plan_id: string;
  amount_cents: number;
  payment_method: string | null;
  payment_status: string;
  payment_id: string | null;
  input_quota_granted: number;
  output_quota_granted: number;
  paid_at: string | null;
  created_at: string;
}

export interface CreateOrderResponse {
  order_id: string;
  order_no: string;
  plan_id: string;
  amount_cents: number;
  input_quota_granted: number;
  output_quota_granted: number;
  payment_status: string;
  checkout_url: string | null;
}
