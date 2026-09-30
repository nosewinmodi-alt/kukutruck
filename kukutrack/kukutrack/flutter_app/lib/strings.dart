import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Minimal English / Kiswahili strings. Missing keys fall back to English.
class Strings {
  static final lang = ValueNotifier<String>('en');

  static Future<void> load() async {
    lang.value = (await SharedPreferences.getInstance()).getString('lang') ?? 'en';
  }

  static Future<void> toggle() async {
    lang.value = lang.value == 'en' ? 'sw' : 'en';
    await (await SharedPreferences.getInstance()).setString('lang', lang.value);
  }

  static String t(String k) => _m[lang.value]?[k] ?? _m['en']![k] ?? k;

  static const Map<String, Map<String, String>> _m = {
    'en': {
      'login': 'Log in', 'register': 'Create account', 'phone': 'Phone (07…)', 'password': 'Password',
      'name': 'Your name', 'farm': 'Farm name', 'consent': 'I agree to the Privacy Policy',
      'birds': 'Live birds', 'eggsToday': 'Eggs today', 'eggs7': 'Eggs (7 days)', 'flocks': 'Flocks',
      'notLogged': 'Not logged today', 'day': 'Day', 'mortality': 'Mortality', 'henday': 'Hen-day %', 'fcr': 'FCR',
      'profit': 'Profit', 'logToday': "Today's record", 'eggs': 'Eggs collected', 'cracked': 'Cracked',
      'deaths': 'Deaths', 'feed': 'Feed used (kg)', 'save': 'Save', 'vacc': 'Vaccinations', 'done': 'Done',
      'savedOffline': 'No network - saved on phone, will sync', 'saved': 'Saved', 'synced': 'Synced',
      'logout': 'Log out', 'lang': 'Kiswahili', 'pending': 'waiting to sync', 'none': 'Nothing here yet',
      'a_mortality_high': 'High deaths today', 'a_mortality_critical': 'Very high deaths - call your vet',
      'a_egg_drop': 'Egg production dropped', 'a_vaccination_due': 'Vaccination due', 'a_low_stock': 'Low stock',
    },
    'sw': {
      'login': 'Ingia', 'register': 'Fungua akaunti', 'phone': 'Simu (07…)', 'password': 'Nenosiri',
      'name': 'Jina lako', 'farm': 'Jina la shamba', 'consent': 'Nakubali Sera ya Faragha',
      'birds': 'Kuku hai', 'eggsToday': 'Mayai leo', 'eggs7': 'Mayai (siku 7)', 'flocks': 'Makundi',
      'notLogged': 'Haijarekodiwa leo', 'day': 'Siku', 'mortality': 'Vifo %', 'henday': 'Uzalishaji %',
      'profit': 'Faida', 'logToday': 'Rekodi ya leo', 'eggs': 'Mayai yaliyokusanywa', 'cracked': 'Yaliyopasuka',
      'deaths': 'Vifo', 'feed': 'Chakula (kg)', 'save': 'Hifadhi', 'vacc': 'Chanjo', 'done': 'Imefanyika',
      'savedOffline': 'Hakuna mtandao - imehifadhiwa, itatumwa baadaye', 'saved': 'Imehifadhiwa', 'synced': 'Imetumwa',
      'logout': 'Toka', 'lang': 'English', 'pending': 'inasubiri kutumwa', 'none': 'Hakuna bado',
      'a_mortality_high': 'Vifo vingi leo', 'a_mortality_critical': 'Vifo vingi sana - mwite daktari',
      'a_egg_drop': 'Mayai yameshuka', 'a_vaccination_due': 'Chanjo inakaribia', 'a_low_stock': 'Bidhaa inaisha',
    },
  };
}
