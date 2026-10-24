/**
 * 永远指向最新值的 ref。
 *
 * 用途：effect 想用一个每次 render 都换身份的回调（比如父组件传进来的
 * onClose），但又不想因为身份变化就重跑 effect —— 重跑的代价是重新抓
 * 「打开时焦点在哪」、重新 focus 第一个字段，用户正在打字的地方就被抢走。
 *
 * 存进 ref 后，effect 只依赖 open，回调始终是这一轮 render 的那个。
 */
import { useRef } from "react";

export function useLatest<T>(value: T): { readonly current: T } {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
