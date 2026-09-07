import os
import sys
import html
import asyncio
import requests
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from .withdraw_db import (
    safe_get_db, 
    get_user_doc, 
    extract_user_balance, 
    extract_usd_balance, 
    get_current_withdraw_tier,
    ZNX_CONTRACT_ADDRESS
)

withdraw_bp = Blueprint('withdraw_bp', __name__)

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_WALLET_MNEMONIC = os.getenv("ADMIN_WALLET_MNEMONIC", "").strip()

def transfer_znx_onchain(to_address_str, amount_znx):
    """إرسال عملة ZNX حقيقياً على شبكة TON للبلوكشين عبر محفظة V4R2 المعتمدة"""
    if not ADMIN_WALLET_MNEMONIC:
        print("❌ خطأ: ADMIN_WALLET_MNEMONIC غير معرّف في متغيرات البيئة!")
        return False, None, "لم يتم ضبط الكلمات المفتاحية (ADMIN_WALLET_MNEMONIC) في إعدادات Railway."

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            task = loop.create_task(_async_transfer_znx(ADMIN_WALLET_MNEMONIC, to_address_str, amount_znx))
            return loop.run_until_complete(asyncio.wait_for(task, timeout=45.0))
        finally:
            loop.close()
    except asyncio.TimeoutError:
        print("❌ خطأ: استغرق الاتصال بشبكة TON وقتاً أطول من اللازم.")
        return False, None, "استجابة شبكة TON بطيئة، يرجى إعادة المحاولة."
    except Exception as e:
        print(f"❌ خطأ أثناء تنفيذ تحويل البلوكشين: {e}")
        return False, None, f"فشل التحويل الشبكي: {str(e)}"

async def _async_transfer_znx(mnemonic_str, to_address_str, amount_znx):
    try:
        from pytoniq import LiteBalancer, Address, begin_cell
    except ImportError:
        return False, None, "مكتبة pytoniq غير مثبتة على السيرفر! تأكد من إضافتها إلى requirements.txt"

    clean_recipient = str(to_address_str or "").strip().replace(" ", "").replace("\n", "").replace("\r", "")
    clean_contract = str(ZNX_CONTRACT_ADDRESS or "").strip().replace(" ", "").replace("\n", "").replace("\r", "")

    mnemonics = mnemonic_str.strip().split()
    if len(mnemonics) not in [12, 24]:
        return False, None, "الكلمات المفتاحية ADMIN_WALLET_MNEMONIC غير صالحة (يجب أن تكون 12 أو 24 كلمة)."

    try:
        master_addr = Address(clean_contract)
    except Exception:
        return False, None, f"عنوان عقد العملة غير صالح: '{clean_contract}'"

    try:
        recipient_addr = Address(clean_recipient)
    except Exception:
        return False, None, f"عنوان محفظة المستخدم غير صالح: '{clean_recipient}'"

    wallet_classes_to_try = []
    try:
        from pytoniq import WalletV4R2
        wallet_classes_to_try.append(("V4R2", WalletV4R2))
    except ImportError:
        pass

    try:
        from pytoniq import WalletV5R1
        wallet_classes_to_try.append(("W5 (V5R1)", WalletV5R1))
    except ImportError:
        pass

    try:
        from pytoniq import WalletV3R2
        wallet_classes_to_try.append(("V3R2", WalletV3R2))
    except ImportError:
        pass

    config_sources = [
        "https://ton.org/global.config.json",
        "https://ton-mainnet-configs.s3.amazonaws.com/ton-global.config.json"
    ]

    last_error = ""

    for attempt, cfg_url in enumerate(config_sources):
        provider = None
        try:
            try:
                provider = LiteBalancer.from_config_url(cfg_url, trust_level=1)
            except Exception:
                provider = LiteBalancer.from_mainnet_config(trust_level=1)

            await provider.start_up()

            wallet = None
            selected_version = None

            for ver_name, WalletClass in wallet_classes_to_try:
                try:
                    w_candidate = await WalletClass.from_mnemonic(provider, mnemonics)
                    acc_state = await provider.get_account_state(w_candidate.address)
                    bal = getattr(acc_state, 'balance', 0)
                    if bal > 30_000_000:
                        wallet = w_candidate
                        selected_version = ver_name
                        print(f"✅ تم اختيار المحفظة: {ver_name} ({w_candidate.address.to_str()})")
                        break
                except Exception as ex:
                    print(f"⚠️ تجربة {ver_name} فشلت: {ex}")
                    continue

            if not wallet and wallet_classes_to_try:
                ver_name, WalletClass = wallet_classes_to_try[0]
                wallet = await WalletClass.from_mnemonic(provider, mnemonics)
                selected_version = ver_name

            if not wallet:
                await provider.close_all()
                return False, None, "تعذر إنشاء المحفظة من الكلمات المفتاحية."

            acc_state = await provider.get_account_state(wallet.address)
            ton_balance = getattr(acc_state, 'balance', 0)
            if ton_balance < 50_000_000:
                await provider.close_all()
                return False, None, f"رصيد TON في محفظة الأدمن ({wallet.address.to_str()}) غير كافٍ لرسوم المعاملة."

            owner_cell = begin_cell().store_address(wallet.address).end_cell()
            res = await provider.run_get_method(
                address=master_addr, 
                method='get_wallet_address', 
                stack=[owner_cell.begin_parse()]
            )

            if not res or len(res) == 0:
                await provider.close_all()
                return False, None, "فشل جلب عنوان محفظة الـ Jetton من عقد العملة الرئيسي."

            admin_jetton_wallet = res[0].load_address()
            nano_jettons = int(round(amount_znx * (10**9)))

            jetton_body = (
                begin_cell()
                .store_uint(0x0f887ea5, 32)
                .store_uint(0, 64)
                .store_coins(nano_jettons)
                .store_address(recipient_addr)
                .store_address(wallet.address)
                .store_maybe_ref(None)
                .store_coins(10_000_000)
                .store_maybe_ref(None)
                .end_cell()
            )

            tx_hash = await wallet.transfer(
                destination=admin_jetton_wallet,
                amount=65_000_000,
                body=jetton_body
            )

            await provider.close_all()
            return True, str(tx_hash), f"🟢 تم تحويل {amount_znx:,.2f} ZNX بنجاح عبر محفظة {selected_version}!"

        except Exception as err:
            last_error = str(err)
            print(f"⚠️ محاولة {attempt + 1} فشلت: {err}")
            if provider:
                try:
                    await provider.close_all()
                except Exception:
                    pass
            if attempt < len(config_sources) - 1:
                await asyncio.sleep(1.0)

    return False, None, f"فشل اتصال البلوكشين: {last_error}"

def execute_admin_decision(tx_id, action):
    """الدالة الأساسية لتنفيذ قرار المشرف وتحديث Firestore وتمرير التحويل"""
    db = safe_get_db()
    if not db or not tx_id:
        return False, "خطأ في الاتصال بقاعدة البيانات!"

    tx_ref = db.collection('processed_txs').document(tx_id)
    tx_doc = tx_ref.get()

    if not tx_doc.exists:
        return False, "لم يتم العثور على طلب السحب في قاعدة البيانات!"

    tx_data = tx_doc.to_dict() or {}
    current_status = tx_data.get('status', 'pending')

    if current_status == 'processing':
        return False, "المعاملة قيد المعالجة حالياً، يرجى الانتظار قليلاً..."

    if current_status != 'pending':
        status_txt = "تم قبولها" if current_status == 'completed' else "تم رفضها"
        return False, f"هذه المعاملة تم معالجتها بالفعل ({status_txt})!"

    user_id = tx_data.get('user_id')
    coins = float(tx_data.get('coins', 0))
    fee_usd = float(tx_data.get('fee_usd', 0.02))
    wallet_address = tx_data.get('wallet_address', '')

    try:
        if action == "approve":
            tx_ref.update({'status': 'processing'})

            onchain_ok, tx_hash, msg = transfer_znx_onchain(wallet_address, coins)
            if not onchain_ok:
                tx_ref.update({'status': 'pending'})
                return False, msg

            update_payload = {
                'status': 'completed',
                'processed_at': firestore.SERVER_TIMESTAMP
            }
            if tx_hash:
                update_payload['tx_hash'] = tx_hash

            tx_ref.update(update_payload)
            return True, f"🟢 تم قبول الطلب وتحويل {coins:,.2f} ZNX بنجاح!"

        else:
            tx_ref.update({
                'status': 'rejected',
                'processed_at': firestore.SERVER_TIMESTAMP
            })

            user_ref, _ = get_user_doc(user_id)
            if user_ref:
                user_ref.update({
                    'znx_balance': firestore.Increment(coins),
                    'usd_balance': firestore.Increment(fee_usd)
                })

            return True, "🔴 تم رفض الطلب وإعادة الرصيد للمستخدم بنجاح!"

    except Exception as e:
        print(f"⚠️ خطأ أثناء تنفيذ قرار السحب: {e}")
        try:
            tx_ref.update({'status': 'pending'})
        except Exception:
            pass
        return False, f"حدث خطأ أثناء المعالجة: {str(e)}"

@withdraw_bp.route('/config', methods=['GET'])
def get_config():
    user_id = request.args.get('user_id') or "5102387551"
    
    user_balance = 0.0
    usd_balance = 0.0
    wallet_address = ""

    _, user_data = get_user_doc(user_id)
    if user_data:
        user_balance = extract_user_balance(user_data)
        usd_balance = extract_usd_balance(user_data)
        wallets = user_data.get('wallets', {})
        if isinstance(wallets, dict):
            wallet_address = wallets.get('ZNX', '')
        if not wallet_address:
            wallet_address = user_data.get('wallet_address', '') or ''

    tier_info = get_current_withdraw_tier()

    return jsonify({
        "success": True,
        "currency": "ZNX",
        "contract_address": ZNX_CONTRACT_ADDRESS,
        "fixed_fee_usd": tier_info.get("fixed_fee_usd", 0.02),
        "min_withdraw_znx": tier_info.get("min_withdraw_znx", 1000.0),
        "current_tier": tier_info,
        "user_balance": user_balance,
        "znx_balance": user_balance,
        "usd_balance": usd_balance,
        "wallet_address": wallet_address
    }), 200

@withdraw_bp.route('/save-wallet', methods=['POST'])
def handle_save_wallet():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    wallet_address = str(data.get('wallet_address', '')).strip()

    if not user_id or not wallet_address:
        return jsonify({"success": False, "message": "يرجى إدخال عنوان المحفظة بشكل صحيح."}), 400

    user_ref, _ = get_user_doc(user_id)
    if not user_ref:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    try:
        user_ref.set({
            'wallets': {'ZNX': wallet_address},
            'wallet_address': wallet_address
        }, merge=True)
        return jsonify({"success": True, "message": "تم حفظ المحفظة بنجاح!"}), 200
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة: {e}")
        return jsonify({"success": False, "message": "حدث خطأ أثناء الحفظ."}), 500

@withdraw_bp.route('/request', methods=['POST'])
def handle_withdraw():
    data = request.json or {}
    user_id = str(data.get('user_id', '')).strip()
    try:
        coins = float(data.get('coins', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "مبلغ السحب غير صالح."}), 400

    wallet_address = str(data.get('wallet_address', '')).strip()

    if not user_id or not wallet_address or coins <= 0:
        return jsonify({"success": False, "message": "بيانات طلب السحب غير مكتملة."}), 400

    db = safe_get_db()
    if not db:
        return jsonify({"success": False, "message": "خطأ في الاتصال بقاعدة البيانات."}), 500

    user_ref, user_data = get_user_doc(user_id)

    if not user_ref or not user_data:
        return jsonify({"success": False, "message": "المستخدم غير موجود."}), 404

    if user_data.get('is_banned', False):
        return jsonify({"success": False, "message": "حسابك معطل ولا يمكنك إجراء عمليات سحب."}), 403

    tier_info = get_current_withdraw_tier()
    min_withdraw = tier_info.get('min_withdraw_znx', 1000.0)
    fixed_fee_usd = tier_info.get('fixed_fee_usd', 0.02)

    current_balance = extract_user_balance(user_data)
    usd_balance = extract_usd_balance(user_data)

    if coins < min_withdraw:
        return jsonify({
            "success": False, 
            "code": "BELOW_MINIMUM",
            "message": f"الحد الأدنى للسحب بالشريحة الحالية هو {min_withdraw:g} ZNX."
        }), 400

    if coins > current_balance:
        return jsonify({
            "success": False, 
            "code": "INSUFFICIENT_ZNX",
            "message": "رصيدك من عملة ZNX غير كافٍ لإتمام عملية السحب."
        }), 400

    if usd_balance < fixed_fee_usd:
        return jsonify({
            "success": False, 
            "code": "INSUFFICIENT_USD",
            "fee_required": fixed_fee_usd,
            "message": f"رسوم السحب لا تكفي! يجب إيداع مبلغ رسوم السحب ${fixed_fee_usd:.2f} USD لإتمام العملية."
        }), 400

    @firestore.transactional
    def update_balances_in_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise Exception("المستخدم غير موجود.")
        
        snap_data = snapshot.to_dict() or {}
        latest_znx = extract_user_balance(snap_data)
        latest_usd = extract_usd_balance(snap_data)

        if coins > latest_znx or latest_usd < fixed_fee_usd:
            raise Exception("رصيدك تغير أثناء المعالجة.")

        updated_znx = round(max(0.0, latest_znx - coins), 6)
        updated_usd = round(max(0.0, latest_usd - fixed_fee_usd), 4)

        transaction.update(ref, {
            'znx_balance': updated_znx,
            'usd_balance': updated_usd
        })
        return updated_znx, updated_usd

    try:
        transaction = db.transaction()
        new_znx_balance, new_usd_balance = update_balances_in_transaction(transaction, user_ref)

        tx_ref = db.collection('processed_txs').document()
        tx_id = tx_ref.id
        tx_ref.set({
            'user_id': user_id,
            'coins': coins,
            'fee_usd': fixed_fee_usd,
            'net_coins': coins,
            'currency': 'ZNX',
            'tier_name': tier_info.get('name', ''),
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP
        })

        notify_admin_withdraw(user_id, coins, fixed_fee_usd, wallet_address, tx_id, tier_info.get('name', ''))

        return jsonify({
            "success": True,
            "message": f"تم تقديم طلب سحب {coins:,.4f} ZNX بنجاح وهو قيد المراجعة!",
            "new_balance": new_znx_balance,
            "new_usd_balance": new_usd_balance
        }), 200

    except Exception as e:
        print(f"⚠️ خطأ معالجة السحب المالي: {e}")
        return jsonify({"success": False, "message": "تعذر إجراء السحب، يرجى إعادة المحاولة."}), 500

def notify_admin_withdraw(user_id, coins, fee_usd, wallet, tx_id, tier_name):
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return

    text = (
        "🚀 <b>طلب سحب ZNX جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> <code>{html.escape(str(user_id))}</code>\n"
        f"📊 <b>الشريحة الحالية:</b> {html.escape(str(tier_name))}\n"
        f"💰 <b>المبلغ المطلوب:</b> <code>{coins:,.4f} ZNX</code>\n"
        f"💵 <b>الرسوم المقتطعة:</b> <code>${fee_usd:.2f} USD</code>\n"
        f"📥 <b>محفظة TON:</b>\n<code>{html.escape(str(wallet))}</code>\n"
        f"🆔 <b>رقم المعاملة:</b> <code>#{html.escape(str(tx_id))}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    reply_markup = {
        "inline_keyboard": [[
            {"text": "موافقة 🟢", "callback_data": f"approve_tx_{tx_id}"},
            {"text": "رفض 🔴", "callback_data": f"reject_tx_{tx_id}"}
        ]]
    }

    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
            timeout=5
        )
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار السحب للأدمن: {e}")
