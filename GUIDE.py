
"""
ملف توجيهي سريع - اختر ما تريد أن تفعل
"""

def main():
    print("\n" + "=" * 80)
    print("  نظام دمج بيانات الإكسيل - دليل توجيهي سريع")
    print("=" * 80 + "\n")
    
    options = {
        "1": {
            "title": "أنا جديد - أريد فهم سريع",
            "description": "اقرأ ملخص سريع في 2-5 دقائق",
            "file": "EXCEL_OVERVIEW.md"
        },
        "2": {
            "title": "أنا مطور - أريد استخدام البيانات",
            "description": "دليل عملي مع أمثلة كود",
            "file": "EXCEL_QUICK_START.md"
        },
        "3": {
            "title": "أنا متقدم - أريد تفاصيل تقنية",
            "description": "ملخص شامل مع تفاصيل كاملة",
            "file": "EXCEL_COMPLETE_SUMMARY.md"
        },
        "4": {
            "title": "أنا محترف - أريد الفنيات المتقدمة",
            "description": "تفاصيل تقنية للمطورين والمسؤولين",
            "file": "EXCEL_INTEGRATION.md"
        },
        "5": {
            "title": "أنا مصمم HTML - أريد مثال جاهز",
            "description": "كود HTML/JS جاهز للنسخ والاستخدام",
            "file": "EXCEL_TEMPLATE_EXAMPLE.html"
        },
        "6": {
            "title": "أريد اختبار النظام",
            "description": "تشغيل اختبار شامل والتحقق من الأداء",
            "action": "test"
        },
        "7": {
            "title": "أريد رؤية ملخص شامل",
            "description": "عرض جميع المعلومات في الشاشة",
            "action": "summary"
        },
        "8": {
            "title": "أريد قائمة جميع الملفات",
            "description": "فهرس كامل لجميع ملفات التوثيق",
            "file": "EXCEL_INDEX.md"
        },
        "0": {
            "title": "خروج",
            "description": "",
            "action": "exit"
        }
    }
    

    for key, value in options.items():
        if key == "0":
            print(f"  {key}. {value['title']}")
        else:
            print(f"  {key}. {value['title']}")
            if value['description']:
                print(f"     → {value['description']}")
    
    print("\n" + "─" * 80 + "\n")
    

    choice = input("اختر رقم الخيار (0-8): ").strip()
    
    if choice in options:
        option = options[choice]
        
        if option.get("action") == "exit":
            print("\n👋 وداعاً! شكراً لاستخدامك النظام.\n")
            return
        
        elif option.get("action") == "test":
            import subprocess
            import os
            print("\n🧪 تشغيل الاختبار...\n")
            try:
                result = subprocess.run(
                    ['python', 'test_excel_integration.py'],
                    cwd=os.path.dirname(__file__) or '.',
                    capture_output=False
                )
                if result.returncode == 0:
                    print("\n✅ الاختبار نجح!")
                else:
                    print("\n❌ الاختبار فشل!")
            except Exception as e:
                print(f"❌ خطأ: {e}")
        
        elif option.get("action") == "summary":
            print("\n📊 عرض الملخص الشامل...\n")
            try:
                result = subprocess.run(
                    ['python', 'SHOW_SUMMARY.py'],
                    cwd=os.path.dirname(__file__) or '.'
                )
            except Exception as e:
                print(f"❌ خطأ: {e}")
        
        elif option.get("file"):
            filename = option['file']
            print(f"\n📖 فتح الملف: {filename}\n")
            print("─" * 80)
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print(content)
            except Exception as e:
                print(f"❌ خطأ في فتح الملف: {e}")
            print("─" * 80)
    else:
        print("\n❌ اختيار غير صحيح!\n")

if __name__ == "__main__":
    import subprocess
    import os
    import sys
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  تم الإيقاف بواسطة المستخدم.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ خطأ: {e}\n")
        sys.exit(1)