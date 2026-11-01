import 'package:go_router/go_router.dart';
import 'screens/splash_screen.dart';
import 'screens/welcome_screen.dart';
import 'screens/login_screen.dart';
import 'screens/register_rib_screen.dart';
import 'screens/register_otp_screen.dart';
import 'screens/register_info_screen.dart';
import 'screens/code_pin_screen.dart';
import 'screens/space_selector_screen.dart';
import 'screens/register_guest_id_screen.dart';
import 'screens/register_sans_rib_screen.dart';
import 'screens/confirm_phone_screen.dart';
import 'screens/register_guest_selfie_screen.dart';
import 'screens/register_guest_complete_screen.dart';
import 'screens/accueil_titulaire_screen.dart';
import 'screens/accueil_beneficiaire_screen.dart';
import 'screens/mes_emissions_screen.dart';
import 'screens/mes_encaissements_screen.dart';
import 'screens/depot_cheque_screen.dart';
import 'screens/confirmation_depot_screen.dart';
import 'screens/alerte_rib_inconnu_screen.dart';
import 'screens/mon_profil_screen.dart';
import 'screens/parametres_screen.dart';
import 'screens/reclamation_chatbot_screen.dart';
import 'screens/conditions_utilisation_screen.dart';
import 'screens/politique_confidentialite_screen.dart';
import 'screens/pin_oublie_screen.dart';
import 'screens/notifications_screen.dart';
import 'screens/changer_code_pin_screen.dart';
import 'screens/cheque_detail_screen.dart';
import 'models/cheque.dart';

final appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const SplashScreen(),
    ),
    GoRoute(
      path: '/welcome',
      builder: (context, state) => const WelcomeScreen(),
    ),
    GoRoute(
      path: '/login',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/register/rib',
      builder: (context, state) => const RegisterRibScreen(),
    ),
    GoRoute(
      path: '/register/confirm-phone',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ConfirmPhoneScreen(
          sessionId:      extra?['sessionId'] as String? ?? '',
          telephoneMasque: extra?['telephoneMasque'] as String? ?? '**********',
        );
      },
    ),
    GoRoute(
      path: '/register/otp',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return RegisterOtpScreen(
          sessionId:       extra?['sessionId'] as String? ?? '',
          telephoneMasque: extra?['telephoneMasque'] as String? ?? '',
        );
      },
    ),
    GoRoute(
      path: '/register/info',
      builder: (context, state) => const RegisterInfoScreen(),
    ),
    GoRoute(
      path: '/register/sans-rib',
      builder: (context, state) => const RegisterSansRibScreen(),
    ),
    GoRoute(
      path: '/register/guest/id',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return RegisterGuestIdScreen(
          fullName:  extra?['fullName']  as String? ?? '',
          phone:     extra?['phone']     as String? ?? '',
          email:     extra?['email']     as String? ?? '',
          cinNumber: extra?['cinNumber'] as String? ?? '',
        );
      },
    ),
    GoRoute(
      path: '/register/guest/selfie',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return RegisterGuestSelfieScreen(
          sessionId: extra?['sessionId'] as String? ?? '',
          fullName:  extra?['fullName']  as String? ?? '',
          phone:     extra?['phone']     as String? ?? '',
          email:     extra?['email']     as String? ?? '',
          cinNumber: extra?['cinNumber'] as String? ?? '',
        );
      },
    ),
    GoRoute(
      path: '/register/guest/complete',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return RegisterGuestCompleteScreen(
          sessionId: extra?['sessionId'] as String? ?? '',
          fullName:  extra?['fullName']  as String? ?? '',
          phone:     extra?['phone']     as String? ?? '',
          email:     extra?['email']     as String? ?? '',
          cinNumber: extra?['cinNumber'] as String? ?? '',
        );
      },
    ),
    GoRoute(
      path: '/pin',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return CodePinScreen(
          loginMode:  extra?['loginMode'] as bool? ?? false,
          telephone:  extra?['telephone'] as String?,
          sessionId:  extra?['sessionId'] as String?,
          tokenInscription: extra?['tokenInscription'] as String?,
        );
      },
    ),
    GoRoute(
      path: '/pin-oublie',
      builder: (context, state) => const PinOublieScreen(),
    ),
    GoRoute(
      path: '/changer-pin',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ChangerCodePinScreen(
          homeRoute: extra?['homeRoute'] as String? ?? '/home/titulaire',
        );
      },
    ),
    GoRoute(
      path: '/notifications',
      builder: (context, state) => const NotificationsScreen(),
    ),
    GoRoute(
      path: '/select-space',
      builder: (context, state) => const SpaceSelectorScreen(),
    ),
    GoRoute(
      path: '/home/titulaire',
      builder: (context, state) => const AccueilTitulaireScreen(),
    ),
    GoRoute(
      path: '/home/beneficiaire',
      builder: (context, state) => const AccueilBeneficiaireScreen(),
    ),
    GoRoute(
      path: '/emissions',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return MesEmissionsScreen(
          homeRoute:   extra?['homeRoute']   as String? ?? '/home/titulaire',
          showScanner: extra?['showScanner'] as bool?   ?? false,
          mode:        EmissionsMode.all,
        );
      },
    ),
    GoRoute(
      path: '/mes-cheques',
      builder: (context, state) => const MesEmissionsScreen(
        homeRoute:   '/home/titulaire',
        mode:        EmissionsMode.pending,
        chequeRoute: '/mes-cheques',
      ),
    ),
    GoRoute(
      path: '/historique/tireur',
      builder: (context, state) => const MesEmissionsScreen(
        homeRoute: '/home/titulaire',
        mode: EmissionsMode.history,
      ),
    ),
    GoRoute(
      path: '/encaissements',
      builder: (context, state) => const MesEncaissementsScreen(),
    ),
    GoRoute(
      path: '/depot',
      builder: (context, state) => const DepotChequeScreen(),
    ),
    GoRoute(
      path: '/depot/confirmation',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ConfirmationDepotScreen(
          numeroCheque: extra?['numeroCheque'] as String?,
          montant:      extra?['montant']      as String?,
          statut:       extra?['statut']       as String?,
        );
      },
    ),
    GoRoute(
      path: '/alert/rib-inconnu',
      builder: (context, state) => const AlerteRibInconnuScreen(),
    ),
    GoRoute(
      path: '/profil',
      builder: (context, state) => const MonProfilScreen(),
    ),
    GoRoute(
      path: '/parametres',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ParametresScreen(
          homeRoute: extra?['homeRoute'] as String? ?? '/home/titulaire',
          showScanner: extra?['showScanner'] as bool? ?? false,
        );
      },
    ),
    GoRoute(
      path: '/chatbot',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ReclamationChatbotScreen(
          homeRoute: extra?['homeRoute'] as String? ?? '/home/titulaire',
          showScanner: extra?['showScanner'] as bool? ?? false,
        );
      },
    ),
    GoRoute(
      path: '/conditions',
      builder: (context, state) => const ConditionsUtilisationScreen(),
    ),
    GoRoute(
      path: '/confidentialite',
      builder: (context, state) => const PolitiqueConfidentialiteScreen(),
    ),
    GoRoute(
      path: '/cheque-detail',
      builder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return ChequeDetailScreen(
          cheque:    extra?['cheque']    as Cheque,
          homeRoute: extra?['homeRoute'] as String? ?? '/home/titulaire',
        );
      },
    ),
  ],
);
