import { useState, useRef, useEffect } from 'react';

const MAX_LEN = 2000;
const PLACEHOLDER =
  "Type your order like you'd text your sales rep... e.g., '3 cases king salmon, 20 lbs jumbo shrimp, 2 flats strawberries'";

export default function OrderInput({ onSubmit, disabled, customerName, value, onChange, onClear }) {
  const [localValue, setLocalValue] = useState(value ?? '');
  const textareaRef = useRef(null);
  const isControlled = value !== undefined && onChange !== undefined;

  const displayValue = isControlled ? value : localValue;
  const setValue = isControlled ? onChange : setLocalValue;

  useEffect(() => {
    if (value !== undefined) setLocalValue(value);
  }, [value]);

  const handleSubmit = () => {
    const trimmed = (isControlled ? value : localValue).trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    if (!isControlled) setLocalValue('');
    onClear?.();
  };

  const len = (isControlled ? value : localValue).length;
  const showCount = len > 1500;

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-gray-700">What do you need today?</label>
      <textarea
        ref={textareaRef}
        aria-label={customerName ? `Order for ${customerName}` : 'Order'}
        placeholder={PLACEHOLDER}
        rows={5}
        maxLength={MAX_LEN}
        value={displayValue}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:border-teal-500 focus:ring-1 focus:ring-teal-500 disabled:bg-gray-100"
      />
      {showCount && (
        <p className="text-sm text-gray-500">
          {len} / {MAX_LEN} characters
        </p>
      )}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!displayValue.trim() || disabled}
        className="w-full rounded-lg bg-teal-600 px-4 py-3 font-medium text-white hover:bg-teal-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
      >
        Place Order 🚀
      </button>
    </div>
  );
}
