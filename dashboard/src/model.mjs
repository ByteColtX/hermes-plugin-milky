export function changedKeys(original, candidate) {
  return Object.fromEntries(
    Object.entries(candidate).filter(
      ([key, value]) => JSON.stringify(value) !== JSON.stringify(original[key]),
    ),
  );
}
export function parseField(key, value) {
  if (["will_policy", "allowed_chats"].includes(key)) return JSON.parse(value);
  if (
    [
      "session_buffer_size",
      "max_local_media_bytes",
      "long_text_forward_threshold",
    ].includes(key)
  ) {
    if (!/^\d+$/.test(value)) throw new Error("请输入非负整数");
    return Number(value);
  }
  return value;
}
export function selectedTargets(items, selected) {
  return items
    .filter((item) => selected.includes(item.sticker_id))
    .map(({ sticker_id, version }) => ({ sticker_id, version }));
}

export function credentialStatusMessage(status) {
  return (
    {
      saved: "凭证已保存；运行状态需要重启后核验。",
      blocked: "宿主管理策略拒绝了凭证修改。",
      unchanged: "凭证未更改。",
      unknown: "无法确认凭证写入结果，请刷新核验。",
    }[status] || "无法确认凭证写入结果，请刷新核验。"
  );
}
