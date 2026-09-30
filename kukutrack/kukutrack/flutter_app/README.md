# KukuTrack - Flutter client

Native Android/iOS app for the KukuTrack API: login/register, dashboard + alerts, flocks, daily record with
**offline queue + automatic sync**, vaccinations, English/Kiswahili.

## Set up
```bash
cd flutter_app
flutter create . --project-name kukutrack --org ke.co.kukutrack   # generates android/ ios/ (keeps lib/ and pubspec.yaml)
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:8000/api        # Android emulator -> local backend
```
Release builds must use an `https://` API_BASE. For a local `http://` backend on a physical Android phone add
`android:usesCleartextTraffic="true"` to the `<application>` tag in `android/app/src/main/AndroidManifest.xml` (debug only).

## Not built yet (same API, straightforward to add)
Money ledger, stock, marketplace, vet cases with camera (`image_picker`), lender-link sharing, forgot-password.
The web app in `../frontend` already has all of these and can be installed on a phone in the meantime.
